import importlib.util
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("fill_records",ROOT/"bot/desk_fill_performance.py")
fills=importlib.util.module_from_spec(spec);spec.loader.exec_module(fills)
NOW=datetime(2026,9,11,tzinfo=timezone.utc)


def bracket(id="entry",side="buy",qty=10,exit_qty=10,entry=100,exit=110,asset="us_equity"):
    return {"id":id,"symbol":"SPY","side":side,"filled_qty":str(qty),"filled_avg_price":str(entry),
            "asset_class":asset,"submitted_at":"2026-08-20T10:00:00Z","filled_at":"2026-08-20T10:00:01Z",
            "legs":[{"id":id+"-exit","symbol":"SPY","side":"sell" if side=="buy" else "buy",
                     "filled_qty":str(exit_qty),"filled_avg_price":str(exit),"filled_at":"2026-08-21T10:00:00Z"}]}


def test_only_owned_complete_families_count():
    result=fills.reconcile([bracket(),bracket(id="other",exit=150),bracket(id="partial",exit_qty=4)],
                           {"entry":"bot-entry","partial":"bot-partial"},"swing","Swing",now=NOW)
    view=fills.period_view(result,30,now=NOW)
    assert view["realized_pnl"]==100 and view["closed_trades"]==1
    assert view["win_rate_pct"]==100 and view["unresolved_count"]==1


def test_manual_same_symbol_exit_is_not_stolen():
    root=bracket(exit_qty=0)
    manual=bracket(id="manual")["legs"][0]
    result=fills.reconcile([root,manual],{"entry":"owned"},"velez","Velez",now=NOW)
    assert result["trades"]==[] and len(result["unresolved_entries"])==1


def test_short_options_and_breakeven():
    roots=[bracket(id="short",side="sell",entry=100,exit=90),
           bracket(id="option",qty=2,exit_qty=2,entry=3,exit=4,asset="us_option"),
           bracket(id="flat",exit=100)]
    result=fills.period_view(fills.reconcile(roots,{o["id"]:o["id"] for o in roots},"x","X",now=NOW),30,now=NOW)
    assert result["realized_pnl"]==300
    assert result["closed_trades"]==3 and result["win_rate_pct"]==66.67


def test_overfilled_exit_does_not_invent_a_trade():
    result=fills.reconcile([bracket(exit_qty=20)],{"entry":"owned"},"x","X",now=NOW)
    assert result["trades"]==[]


def test_period_filters_close_date():
    snapshot=fills.reconcile([bracket()],{"entry":"owned"},"x","X",now=NOW)
    assert fills.period_view(snapshot,7,now=NOW)["closed_trades"]==0
    assert fills.period_view(snapshot,30,now=NOW)["closed_trades"]==1


def test_history_paginates_even_when_nested_page_has_fewer_than_limit():
    class Broker:
        def __init__(self):self.calls=[]
        def _request(self,method,path,params):
            assert method=="GET" and path=="/v2/orders"
            self.calls.append(params)
            return [bracket()] if len(self.calls)==1 else []
    broker=Broker();orders,complete=fills.order_history(broker)
    assert complete and len(orders)==1 and len(broker.calls)==2
    assert "until" in broker.calls[1]


def test_truncated_history_withholds_pnl():
    snapshot=fills.reconcile([bracket()],{"entry":"owned"},"x","X",complete=False,now=NOW)
    assert fills.period_view(snapshot,30,now=NOW)["realized_pnl"] is None

