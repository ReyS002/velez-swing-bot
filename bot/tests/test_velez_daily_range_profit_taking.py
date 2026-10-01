"""Rulebook 2026.10.5/10.6 in the live bot: the daily-range entry gate and the profit-taking partial."""

from datetime import datetime, timedelta, timezone

from bot.core import velez_doctrine as doctrine
from bot.core.types import Bar, Side, Signal
from bot.core.velez_strategy import (
    VelezInstitutionalStrategy,
    daily_atr_from_rows,
    daily_rows_before,
    split_safe_daily_rows,
)
from bot.tests.test_journal_watchlist_approvals import FakeBroker, config
from bot.webhook_server import TradingViewWebhookEngine

# Wed 2026-06-03, 14:30 UTC = 10:30 New York.
SESSION_DAY = datetime(2026, 6, 3, tzinfo=timezone.utc).date()
NOON_UTC = datetime(2026, 6, 3, 14, 30, tzinfo=timezone.utc)


def daily_rows(n=20, rng=2.0, last_day=datetime(2026, 6, 2, tzinfo=timezone.utc)):
    """n completed days with a constant 2.0 true range: daily ATR 2.0."""
    rows = []
    for i in range(n):
        t = last_day - timedelta(days=n - 1 - i)
        rows.append({"o": 100.0, "h": 100.0 + rng / 2, "l": 100.0 - rng / 2, "c": 100.0, "v": 1e6, "t": t})
    return rows


def session_bar(minutes_after_open, o, h, l, c):
    t = datetime(2026, 6, 3, 13, 30, tzinfo=timezone.utc) + timedelta(minutes=minutes_after_open)
    return Bar(timestamp=t, open=o, high=h, low=l, close=c, volume=1000)


def strategy(**doctrine_cfg):
    cfg = {"doctrine": {"enabled": True, "session_windows": False, **doctrine_cfg}}
    return VelezInstitutionalStrategy(cfg)


def signal(symbol="SPY", side=Side.BUY):
    return Signal(symbol=symbol, side=side, reason="elephant_bar", metadata={"play": "elephant_bar"})


def feed_session(strat, symbol, bars):
    ctx = strat._get_context(symbol)
    for b in bars:
        ctx.bars.append(b)


# ── daily rows helpers ──

def test_daily_atr_needs_a_full_window_and_skips_today():
    rows = daily_rows(20)
    assert daily_atr_from_rows(rows) == 2.0
    assert daily_atr_from_rows(rows[:14]) is None  # 15 rows needed for a 14-period ATR
    today = {"o": 100.0, "h": 130.0, "l": 90.0, "c": 120.0, "v": 1.0, "t": datetime(2026, 6, 3, tzinfo=timezone.utc)}
    assert daily_rows_before(rows + [today], SESSION_DAY) == rows


def test_split_sized_gap_restarts_the_daily_history():
    rows = daily_rows(20)
    # A 2-for-1 split on day 10: every price from then on is halved.
    rows[10:] = [{**r, "o": r["o"] / 2, "h": r["h"] / 2, "l": r["l"] / 2, "c": r["c"] / 2} for r in rows[10:]]
    assert split_safe_daily_rows(rows) == rows[10:]
    assert daily_atr_from_rows(rows) is None  # 10 post-split days: no full ATR yet


# ── daily range gate ──

def test_range_used_off_by_default_and_without_a_live_source():
    strat = strategy()
    strat.daily_bars_provider = lambda symbol: daily_rows()
    bar = session_bar(60, 102.0, 102.6, 101.9, 102.5)
    assert strat._range_used(signal(), bar) is None  # rule off
    on = strategy(daily_range=True)
    assert on._range_used(signal(), bar) is None  # no live daily source (backtests, replays)


def test_range_used_measures_todays_move_in_daily_atrs():
    strat = strategy(daily_range=True)
    strat.daily_bars_provider = lambda symbol: daily_rows()
    feed_session(strat, "SPY", [session_bar(0, 100.5, 101.0, 100.0, 100.8), session_bar(30, 100.8, 101.5, 100.6, 101.4)])
    bar = session_bar(60, 101.4, 102.6, 101.3, 102.5)
    # Up 2.5 from today's 100.0 low on a 2.0 daily ATR: 1.25 ATRs used for a long.
    assert abs(strat._range_used(signal(), bar) - 1.25) < 1e-9
    # A short measures down from today's high (102.6): 0.05 ATRs.
    assert abs(strat._range_used(signal(side=Side.SELL), bar) - 0.05) < 1e-9


def test_range_block_moves_the_veto():
    strat = strategy(daily_range=True, range_block=1.5)
    strat.daily_bars_provider = lambda symbol: daily_rows()
    feed_session(strat, "SPY", [session_bar(0, 100.5, 101.0, 100.0, 100.8)])
    bar = session_bar(60, 101.4, 102.6, 101.3, 102.5)
    # 1.25 ATRs used against a 1.5 block: scaled to 0.833, under the rulebook's 1.0 veto.
    used = strat._range_used(signal(), bar)
    assert abs(used - 1.25 / 1.5) < 1e-9


def test_range_used_blocks_a_continuation_entry_in_the_gate():
    strat = strategy(daily_range=True)
    strat.daily_bars_provider = lambda symbol: daily_rows()
    feed_session(strat, "SPY", [session_bar(0, 100.5, 101.0, 100.0, 100.8)])
    bar = session_bar(60, 101.4, 102.6, 101.3, 102.5)
    used = strat._range_used(signal(), bar)
    gate = doctrine.entry_gate("long", "elephant_bar", price=102.5, sma200=None, sma200_slope=None,
                               state=None, near_200=False, range_used=used)
    assert gate["allowed"] is False
    assert "daily_range_exhausted" in gate["reasons"]


def test_range_used_not_enforced_for_non_equities_or_a_failed_fetch():
    strat = strategy(daily_range=True)
    strat.daily_bars_provider = lambda symbol: daily_rows()
    bar = session_bar(60, 101.4, 102.6, 101.3, 102.5)
    assert strat._range_used(signal(symbol="BTC/USD"), bar) is None

    def boom(symbol):
        raise RuntimeError("feed down")

    strat.daily_bars_provider = boom
    assert strat._range_used(signal(), bar) is None
    strat.daily_bars_provider = lambda symbol: daily_rows(10)  # not a full ATR window
    assert strat._range_used(signal(), bar) is None


# ── profit-taking partial in the live lifecycle ──

def lifecycle_engine(monkeypatch, tmp_path, trigger):
    monkeypatch.setenv("VELEZ_LIFECYCLE_AUTO_EXECUTE", "true")
    monkeypatch.setenv("VELEZ_EXECUTE_ORDERS", "true")
    monkeypatch.setenv("VELEZ_JOURNAL_DB", str(tmp_path / "journal.sqlite3"))
    cfg = config()
    cfg["webhook"]["execute_orders"] = True
    cfg["strategy"] = {
        "exits": {
            "auto_flatten": {"enabled": False},
            "partials_auto_execute": {"enabled": True, "trigger": trigger, "first_r": 1.0, "first_pct": 0.5,
                                      "second_r": 2.0, "second_pct": 0.25},
        }
    }
    broker = FakeBroker()
    engine = TradingViewWebhookEngine(cfg, broker=broker)
    monkeypatch.setattr(engine, "_velez_live_management", lambda position: None)
    monkeypatch.setattr(engine, "_velez_partial_window_open", lambda symbol: True)  # tests run at any hour
    return engine, broker


def position(current_r):
    entry_ts = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    return {
        "symbol": "SPY", "qty": "100", "side": "long", "entry_price": 500.0, "stop_price": 495.0,
        "current_r_multiple": current_r, "stop_source": "broker_order",
        "linked_decision": {"timestamp": entry_ts, "stop_price": 495.0},
    }


def partial_orders(broker):
    return [o for o in broker.submitted if str(o.get("client_order_id", "")).startswith("velez-partial-")]


def test_profit_taking_trigger_takes_the_first_partial_at_the_verdict(monkeypatch, tmp_path):
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    monkeypatch.setattr(engine, "_velez_profit_taking_verdict", lambda p: {"status": "take_partial", "pushes": 3})
    actions = engine._auto_lifecycle_actions(positions=[position(0.6)], open_orders=[], guardrails=[])
    assert [a["action"] for a in actions] == ["partial_first_r"]
    assert partial_orders(broker)[0]["qty"] == "50"
    # Taken once: the next pass doesn't sell again.
    engine._auto_lifecycle_actions(positions=[position(0.7)], open_orders=[], guardrails=[])
    assert len(partial_orders(broker)) == 1


def test_profit_taking_trigger_holds_on_a_hold_verdict(monkeypatch, tmp_path):
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    monkeypatch.setattr(engine, "_velez_profit_taking_verdict", lambda p: {"status": "hold"})
    engine._auto_lifecycle_actions(positions=[position(1.4)], open_orders=[], guardrails=[])
    # At 1.4R the R-multiple trigger would have sold; the verdict says hold.
    assert partial_orders(broker) == []


def test_unreadable_verdict_falls_back_to_the_r_multiple_partial(monkeypatch, tmp_path):
    for verdict in ({"status": "unknown"}, None):
        engine, broker = lifecycle_engine(monkeypatch, tmp_path / str(bool(verdict)), "velez_profit_taking")
        monkeypatch.setattr(engine, "_velez_profit_taking_verdict", lambda p, v=verdict: v)
        engine._auto_lifecycle_actions(positions=[position(0.6)], open_orders=[], guardrails=[])
        assert partial_orders(broker) == []  # below 1R: nothing either way
        engine._auto_lifecycle_actions(positions=[position(1.4)], open_orders=[], guardrails=[])
        assert [o["qty"] for o in partial_orders(broker)] == ["50"]


def test_profit_taking_trigger_never_sells_a_loser(monkeypatch, tmp_path):
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    calls = []
    monkeypatch.setattr(engine, "_velez_profit_taking_verdict", lambda p: calls.append(p) or {"status": "take_profits"})
    engine._auto_lifecycle_actions(positions=[position(-0.2)], open_orders=[], guardrails=[])
    assert partial_orders(broker) == [] and calls == []


def test_default_trigger_is_unchanged(monkeypatch, tmp_path):
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "r_multiple")
    monkeypatch.setattr(engine, "_velez_profit_taking_verdict", lambda p: (_ for _ in ()).throw(AssertionError("not used")))
    engine._auto_lifecycle_actions(positions=[position(1.1)], open_orders=[], guardrails=[])
    assert [o["qty"] for o in partial_orders(broker)] == ["50"]


def test_profit_taking_verdict_reads_pushes_and_daily_atr(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    # Three pushes after the entry bar on 15-minute bars in Wednesday's session (EDT: 14:00 UTC = 10:00 ET).
    start = datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc)
    prices = [(100, 101, 99.5, 100.8), (100.8, 101.5, 100.5, 101.2), (101.2, 101.3, 100.9, 101.0),
              (101.0, 102.0, 100.9, 101.8), (101.8, 101.9, 101.4, 101.5), (101.5, 102.6, 101.4, 102.4)]
    bars = [Bar(timestamp=start + timedelta(minutes=15 * i), open=o, high=h, low=l, close=c, volume=1000)
            for i, (o, h, l, c) in enumerate(prices)]
    engine.scanner_config["timeframe"] = "15Min"
    monkeypatch.setattr(engine, "_fetch_scanner_bars", lambda symbol, asset_type, timeframe=None: bars)
    monkeypatch.setattr(engine, "_velez_daily_rows", lambda symbol: daily_rows(70))
    monkeypatch.setattr(engine, "_velez_session_bars", lambda symbol, since_day=None: [])
    pos = position(0.5)
    pos["linked_decision"]["timestamp"] = (start + timedelta(minutes=5)).isoformat()
    verdict = engine._velez_profit_taking_verdict(pos)
    assert verdict["pushes"] == 3
    assert verdict["daily_atr"] == 2.0
    assert verdict["status"] in {"take_partial", "take_profits"}


def test_profit_taking_verdict_none_without_entry_time(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    pos = position(0.5)
    pos["linked_decision"] = {}
    assert engine._velez_profit_taking_verdict(pos) is None


def test_partials_block_beside_exits_is_read(monkeypatch, tmp_path):
    """config.yaml keeps partials_auto_execute beside `exits`; that block must take effect."""
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "r_multiple")
    engine.config["strategy"] = {
        "exits": {"auto_flatten": {"enabled": False}},
        "partials_auto_execute": {"enabled": True, "trigger": "velez_profit_taking", "second_r": 2.0, "first_pct": 0.5},
    }
    monkeypatch.setattr(engine, "_velez_profit_taking_verdict", lambda p: {"status": "hold"})
    engine._auto_lifecycle_actions(positions=[position(1.2)], open_orders=[], guardrails=[])
    assert partial_orders(broker) == []  # the verdict trigger is in charge, not the 1R default


def test_shipped_config_enables_profit_taking_not_daily_range():
    import yaml
    from pathlib import Path

    cfg = yaml.safe_load((Path(__file__).resolve().parents[1] / "config.yaml").read_text())
    assert cfg["velez_strategy"]["doctrine"]["daily_range"] is False  # daily bars: n/a
    assert cfg["velez_strategy"]["doctrine"]["range_block"] == 1.0
    assert cfg["strategy"]["partials_auto_execute"]["trigger"] == "velez_profit_taking"


def test_profit_taking_verdict_on_daily_bars_measures_the_hold(monkeypatch, tmp_path):
    """Swing: no intraday session, so the move is measured from its origin within the hold."""
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    engine.scanner_config["timeframe"] = "1Day"
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    # Daily bars labeled at midnight UTC; the last one is 3 days old so all are closed.
    closes = [100, 101, 103, 102.5, 104.5, 104, 106.5]
    bars = [Bar(timestamp=today - timedelta(days=3 + len(closes) - 1 - i), open=c - 0.5, high=c + 0.5,
                low=c - 1.0, close=c, volume=1e6) for i, c in enumerate(closes)]
    monkeypatch.setattr(engine, "_fetch_scanner_bars", lambda symbol, asset_type, timeframe=None: bars)
    monkeypatch.setattr(engine, "_velez_daily_rows", lambda symbol: daily_rows(70, last_day=today - timedelta(days=1)))
    pos = position(0.8)
    pos["linked_decision"]["timestamp"] = (bars[1].timestamp + timedelta(hours=15)).isoformat()
    verdict = engine._velez_profit_taking_verdict(pos)
    assert verdict["pushes"] == 3
    # Origin = the hold's lowest low before the latest high (bar 1's low 100.0): 6.5 / 2.0 ATR.
    assert verdict["move_in_daily_atr"] == 3.25
    assert verdict["status"] == "take_profits"
