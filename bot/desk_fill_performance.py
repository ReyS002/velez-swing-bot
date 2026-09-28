"""Read-only reconciliation of journal-owned Alpaca bracket order families."""
from __future__ import annotations
import json
import math
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path


def number(value):
    try:
        value=float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def stamp(value):
    try:
        result=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result
    except (ValueError, TypeError):
        return None


def ownership(path):
    db=sqlite3.connect(Path(path).resolve().as_uri()+"?mode=ro",uri=True,timeout=3)
    try:
        rows=db.execute("SELECT alert_ref,broker_response_json FROM decisions WHERE broker_response_json NOT IN ('{}','null','')").fetchall()
    finally:
        db.close()
    result={}
    for ref,raw in rows:
        try: order=json.loads(raw)
        except (ValueError,TypeError): continue
        if isinstance(order,dict) and order.get("id") and ref:
            result[str(order["id"])]=str(ref)
    return result


def order_history(broker, max_pages=30):
    result={};until=None
    for _ in range(max_pages):
        params={"status":"all","nested":"true","limit":500,"direction":"desc"}
        if until:params["until"]=until
        page=broker._request("GET","/v2/orders",params=params)
        if not isinstance(page,list):raise ValueError("Invalid order history")
        if not page:return list(result.values()),True
        added=0
        for item in page:
            if item.get("id") and item["id"] not in result:
                result[item["id"]]=item;added+=1
        times=[stamp(item.get("submitted_at") or item.get("created_at")) for item in page]
        times=[value for value in times if value]
        if not times or not added:return list(result.values()),False
        # Include the boundary again; IDs deduplicate it. An unchanged page fails closed.
        oldest=min(times)
        next_until=oldest.isoformat()
        if until==next_until:
            next_until=(oldest-timedelta(microseconds=1)).isoformat()
        until=next_until
    return list(result.values()),False


def reconcile(orders, owned, bot_id, label, complete=True, now=None):
    now=now or datetime.now(timezone.utc)
    all_orders={}
    def flatten(order):
        if order.get("id"):all_orders[str(order["id"])]=order
        for leg in order.get("legs") or []:flatten(leg)
    for order in orders:flatten(order)
    trades=[];unresolved=[];seen_exits=set();matched=0
    for order_id,ref in owned.items():
        entry=all_orders.get(order_id)
        if not entry:continue
        matched+=1
        qty=number(entry.get("filled_qty")) or 0
        price=number(entry.get("filled_avg_price"))
        if qty<=0 or price is None:continue
        side=str(entry.get("side") or "")
        if side not in {"buy","sell"}:continue
        symbol=entry.get("symbol")
        exits=[];family_seen=set()
        def family(order):
            key=str(order.get("id") or "")
            if key in family_seen:return
            family_seen.add(key)
            if key!=order_id and order.get("symbol")==symbol and order.get("side")!=side:
                q=number(order.get("filled_qty")) or 0;p=number(order.get("filled_avg_price"))
                if q>0 and p is not None and stamp(order.get("filled_at")):
                    exits.append((order,q,p))
            for leg in order.get("legs") or []:family(leg)
            replacement=all_orders.get(str(order.get("replaced_by") or ""))
            if replacement:family(replacement)
        family(entry)
        exited=sum(q for _,q,_ in exits)
        # Never attach a same-symbol manual close or another bot's exit by guesswork.
        if abs(exited-qty)>max(1e-7,qty*1e-8) or not exits or any(str(o.get("id")) in seen_exits for o,_,_ in exits):
            unresolved.append({"reference":ref,"symbol":symbol,"entry_qty":qty,"linked_exit_qty":exited,
                               "reason":"Open, partially closed, or missing a linked exit"})
            continue
        multiplier=100 if entry.get("asset_class")=="us_option" else 1
        pnl=sum((p-price)*q for _,q,p in exits)*(1 if side=="buy" else -1)*multiplier
        for o,_,_ in exits:seen_exits.add(str(o["id"]))
        trades.append({"reference":ref,"symbol":symbol,"closed_at":max(stamp(o["filled_at"]) for o,_,_ in exits).isoformat(),
                       "pnl":round(pnl,2),"status":"closed","quantity":qty,"entry_price":price,
                       "exit_price":sum(q*p for _,q,p in exits)/qty})
    return {"ok":True,"bot_id":bot_id,"label":label,"source":"Broker fills · journal-owned order families",
            "as_of":now.isoformat(),"history_complete":complete,"trades":trades,"unresolved_entries":unresolved,
            "journal_orders_not_in_broker_history":len(owned)-matched,
            "note":"Closed bracket trades belonging to this bot, reconciled to broker fill quantities and prices. P&L is before fees. Open positions, partial exits and unlinked manual closes are excluded; they are not counted as wins or losses."}


def period_view(snapshot,days=30,now=None):
    now=now or datetime.now(timezone.utc);start=now-timedelta(days=days)
    trades=[t for t in snapshot.get("trades",[]) if stamp(t.get("closed_at")) and start<=stamp(t["closed_at"])<=now]
    count=len(trades)
    result={k:v for k,v in snapshot.items() if k!="trades"}
    result.update({"period_days":days,"closed_trades":count,"priced_trades":count,"missing_pnl":0,
                   "realized_pnl":round(sum(t["pnl"] for t in trades),2) if snapshot.get("history_complete") else None,
                   "win_rate_pct":round(sum(t["pnl"]>0 for t in trades)/count*100,2) if count else None,
                   "trades":sorted(trades,key=lambda t:t["closed_at"],reverse=True)[:100],
                   "trade_list_truncated":count>100,
                   "unresolved_count":len(snapshot.get("unresolved_entries",[])),
                   "stale":not stamp(snapshot.get("as_of")) or (now-stamp(snapshot["as_of"])).total_seconds()>900})
    result.pop("unresolved_entries",None)
    return result


class FillPerformance:
    def __init__(self,engine,bot_id,label):
        self.engine=engine;self.bot_id=bot_id;self.label=label
        self.path=Path(engine.journal.path).parent/"desk-performance.json"
        self.snapshot=None;self.last_error=False;self.stop_event=threading.Event();self.thread=None
        broker=getattr(engine,"broker",None)
        self.supported=broker is not None and "alpaca" in type(broker).__module__.lower() and hasattr(broker,"_request")

    def refresh(self):
        orders,complete=order_history(self.engine.broker)
        result=reconcile(orders,ownership(self.engine.journal.path),self.bot_id,self.label,complete)
        # Atomic replacement lets Velez read Swing without holding or altering its database.
        temp=self.path.with_name(self.path.name+f".{os.getpid()}.{threading.get_ident()}.tmp")
        temp.write_text(json.dumps(result,allow_nan=False))
        os.replace(temp,self.path)
        self.snapshot=result;self.last_error=False

    def start(self):
        if not self.supported or self.thread:return
        def run():
            while not self.stop_event.is_set():
                try:self.refresh()
                except Exception:self.last_error=True
                if self.stop_event.wait(60 if self.last_error else 300):break
        self.thread=threading.Thread(target=run,name="desk-fill-performance",daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def view(self,days):
        if not self.snapshot:return None
        result=period_view(self.snapshot,days)
        if self.last_error:result["refresh_failed"]=True
        return result
