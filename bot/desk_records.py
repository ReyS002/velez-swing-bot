"""Read-only desk research and bot-attributed journal performance.

Account snapshots and lifecycle milestones are deliberately not trade outcomes.
Peer journals are explicit operator-configured read-only sources, never client paths.
"""
from __future__ import annotations
import json
import math
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import Query
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from .desk_fill_performance import FillPerformance, period_view


@contextmanager
def connect(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=3)
    db.row_factory = sqlite3.Row
    try:
        yield db
    finally:
        db.close()


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def research_payload(path, query="", offset=0, limit=20):
    query = str(query or "").strip()[:240]
    term = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    where = "WHERE topic LIKE ? ESCAPE '\\' OR result_json LIKE ? ESCAPE '\\'"
    with connect(path) as db:
        total = db.execute("SELECT count(*) FROM research_notes " + where, (term, term)).fetchone()[0]
        rows = db.execute(
            "SELECT id,timestamp,topic,result_json FROM research_notes " + where +
            " ORDER BY datetime(timestamp) DESC,id DESC LIMIT ? OFFSET ?",
            (term, term, limit, offset),
        ).fetchall()
    notes = []
    for row in rows:
        try:
            result = json.loads(row["result_json"] or "{}")
        except (ValueError, TypeError):
            result = {}
        if not isinstance(result, dict):
            result = {}
        notes.append({
            "id": row["id"], "timestamp": row["timestamp"], "topic": row["topic"],
            "symbol": result.get("symbol"), "text": result.get("reply") or result.get("summary") or "",
            "provider": result.get("provider"),
        })
    return {"ok": True, "notes": notes, "total": total, "offset": offset, "limit": limit, "query": query}


def journal_performance(path, bot_id, label, days=30, now=None):
    now = now or datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    with connect(path) as db:
        # A broker submission in this journal establishes ownership. A symbol alone does not.
        decisions = db.execute(
            "SELECT alert_ref,broker_response_json FROM decisions "
            "WHERE broker_response_json IS NOT NULL AND broker_response_json NOT IN ('{}','null','')"
        ).fetchall()
        owned = set()
        for decision in decisions:
            try:
                response = json.loads(decision["broker_response_json"] or "{}")
            except (ValueError, TypeError):
                continue
            if isinstance(response, dict) and response.get("id") and decision["alert_ref"]:
                owned.add(decision["alert_ref"])
        rows = db.execute(
            "SELECT * FROM trade_outcomes WHERE datetime(timestamp)>=datetime(?) "
            "AND datetime(timestamp)<=datetime(?) ORDER BY datetime(timestamp) DESC,id DESC",
            (start.isoformat(), now.isoformat()),
        ).fetchall()
    trades, seen, excluded = [], set(), 0
    for row in rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except (ValueError, TypeError):
            payload = {}
        # One_R, open_position and stale/guardrail observations can carry floating P&L.
        # They are not closed trades, even if a numeric P&L happens to be present.
        status = str(row["status"] or "").lower()
        terminal = payload.get("terminal") is True or status in {"won", "lost", "closed", "filled_closed"}
        if not terminal or status.startswith("guardrail") or status.endswith("_stale"):
            continue
        ref = row["alert_ref"]
        if ref not in owned:
            excluded += 1
            continue
        if ref in seen:
            continue
        seen.add(ref)
        trades.append({
            "reference": ref, "symbol": row["symbol"], "closed_at": row["timestamp"],
            "pnl": number(row["pnl"]), "status": status,
        })
    priced = [trade for trade in trades if trade["pnl"] is not None]
    wins = sum(trade["pnl"] > 0 for trade in priced)
    return {
        "ok": True, "bot_id": bot_id, "label": label, "source": "Bot-owned journal closes",
        "period_days": days, "as_of": now.isoformat(), "closed_trades": len(trades),
        "priced_trades": len(priced), "missing_pnl": len(trades) - len(priced),
        "realized_pnl": round(sum(trade["pnl"] for trade in priced), 2) if priced else None,
        "win_rate_pct": round(wins / len(priced) * 100, 2) if priced else None,
        "wins": wins, "losses": sum(trade["pnl"] < 0 for trade in priced),
        "breakeven": sum(trade["pnl"] == 0 for trade in priced),
        "unlinked_closes_excluded": excluded, "trades": trades[:100],
        "trade_list_truncated": len(trades) > 100,
        "note": "Realized journal P&L for orders submitted by this bot. Account-wide balances, open P&L and lifecycle milestones are excluded. Win rate includes breakeven closes and only trades with recorded P&L.",
    }


def swarm_performance(path, days=30, now=None):
    now = now or datetime.now(timezone.utc)
    score = json.loads(Path(path).read_text())
    updated = datetime.fromisoformat(score["generated_at"].replace("Z", "+00:00"))
    start = now - timedelta(days=days)
    trades = []
    for item in score.get("trades", []):
        if not item.get("is_closed") or not item.get("closed_at"):
            continue
        closed = datetime.fromisoformat(item["closed_at"].replace("Z", "+00:00"))
        if start <= closed <= now:
            trades.append({"reference": item.get("order_id"), "symbol": item.get("symbol"),
                           "closed_at": item["closed_at"], "pnl": number(item.get("pnl_dollars")),
                           "strategy": item.get("bot")})
    priced = [trade for trade in trades if trade["pnl"] is not None]
    return {
        "ok": True, "bot_id": "swarm", "label": "Swarm · paper", "source": "Swarm paper fill scorecard",
        "period_days": days, "as_of": updated.isoformat(), "stale": (now-updated).total_seconds() > 7200,
        "closed_trades": len(trades), "priced_trades": len(priced),
        "missing_pnl": len(trades)-len(priced),
        "realized_pnl": round(sum(t["pnl"] for t in priced), 2) if priced else None,
        "win_rate_pct": round(sum(t["pnl"] > 0 for t in priced)/len(priced)*100, 2) if priced else None,
        "trades": trades[:100], "trade_list_truncated": len(trades)>100,
        "note": "Paper trades reconciled by Swarm's own scorecard. Historical backtests and crypto shadow simulations are excluded.",
    }


def install_desk_records(app, engine, bot_id, label):
    collector = FillPerformance(engine, bot_id, label)
    app.state.desk_records = collector
    def performance(days):
        own = collector.view(days)
        if own is None:
            own = ({"ok": False, "pending": not collector.last_error, "bot_id": bot_id, "label": label,
                    "note": ("Broker fill history is temporarily unavailable. Check the broker connection and retry shortly."
                             if collector.last_error else "Reconciling this bot's broker fills. This view will update shortly.")}
                   if collector.supported else journal_performance(engine.journal.path, bot_id, label, days))
        cards = [own]
        if bot_id == "velez":
            for key, peer_id, peer_label, reader in [
                ("DESK_SWING_JOURNAL", "swing", "Swing Bot", journal_performance),
                ("DESK_SWARM_SCORECARD", "swarm", "Swarm · paper", swarm_performance),
            ]:
                path = os.getenv(key)
                if not path:
                    continue
                try:
                    if peer_id == "swing":
                        snapshot = json.loads((Path(path).parent / "desk-performance.json").read_text())
                        if snapshot.get("bot_id") != "swing":
                            raise ValueError("Unexpected performance source")
                        card = period_view(snapshot, days)
                    else:
                        card = reader(path, days)
                except (OSError, ValueError, sqlite3.Error, KeyError):
                    card = {"ok": False, "bot_id": peer_id, "label": peer_label,
                            "note": "This performance source is temporarily unavailable."}
                cards.append(card)
        return {"ok": True, "current_bot": bot_id, "cards": cards}

    @app.get("/api/desk/research")
    async def saved_research(q: str = "", offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=50)):
        data = await run_in_threadpool(research_payload, engine.journal.path, q, offset, limit)
        return JSONResponse(data, headers={"Cache-Control": "no-store"})

    @app.get("/api/desk/performance")
    async def desk_performance(days: int = Query(30, ge=1, le=365)):
        data = await run_in_threadpool(performance, days)
        return JSONResponse(data, headers={"Cache-Control": "no-store"})
