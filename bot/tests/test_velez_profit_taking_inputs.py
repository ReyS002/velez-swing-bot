"""The inputs behind the daily-range and profit-taking rules: session bars, timeframes, entry time."""

from datetime import datetime, timedelta, timezone

from bot.core.types import Bar, Side
from bot.core.velez_strategy import session_high_low_overlap, session_overlap_bars, utc_daily_rows
from bot.tests.test_velez_daily_range_profit_taking import (
    daily_rows,
    lifecycle_engine,
    partial_orders,
    position,
    signal,
    strategy,
)


def hour_bar(et_hour, o, h, l, c, day=3):
    # June 2026 is EDT (UTC-4): 09:00 ET = 13:00 UTC.
    t = datetime(2026, 6, day, et_hour + 4, tzinfo=timezone.utc)
    return {"o": o, "h": h, "l": l, "c": c, "v": 1.0, "t": t}


def test_session_bars_keep_the_hour_that_straddles_the_open():
    bars = [hour_bar(15, 99, 99.5, 98, 99, day=2), hour_bar(9, 100, 101, 97.0, 100.5), hour_bar(10, 100.5, 102, 100, 101.8),
            hour_bar(11, 101.8, 102.5, 101.5, 102.2)]
    today = session_overlap_bars(bars)
    assert [b["t"].hour for b in today] == [13, 14, 15]  # the 09:00 ET bar (09:30-10:00) is in
    assert session_high_low_overlap(bars) == (102.5, 97.0)


def test_session_bars_drop_premarket_and_after_hours():
    bars = [hour_bar(7, 1, 1, 1, 1), hour_bar(8, 1, 1, 1, 1), hour_bar(9, 2, 2, 2, 2), hour_bar(16, 3, 3, 3, 3)]
    assert [b["t"].hour for b in session_overlap_bars(bars)] == [13]


def test_range_used_counts_the_opening_hour():
    strat = strategy(daily_range=True)
    strat.daily_bars_provider = lambda symbol: daily_rows()
    ctx = strat._get_context("SPY")
    for b in (hour_bar(9, 100, 100.5, 99.0, 100.2), hour_bar(10, 100.2, 100.9, 100.1, 100.8)):
        ctx.bars.append(Bar(timestamp=b["t"], open=b["o"], high=b["h"], low=b["l"], close=b["c"], volume=1))
    bar = Bar(timestamp=hour_bar(11, 0, 0, 0, 0)["t"], open=100.8, high=101.2, low=100.7, close=101.1, volume=1)
    # Up 2.1 from the 99.0 low made in the opening half hour, on a 2.0 daily ATR.
    assert abs(strat._range_used(signal(), bar) - 1.05) < 1e-9


def test_utc_daily_rows_aggregate_round_the_clock_bars():
    t0 = datetime(2026, 6, 1, tzinfo=timezone.utc)
    bars = [{"o": 10 + i, "h": 11 + i, "l": 9 + i, "c": 10.5 + i, "v": 1, "t": t0 + timedelta(hours=12 * i)} for i in range(6)]
    rows = utc_daily_rows(bars, before=datetime(2026, 6, 3, tzinfo=timezone.utc).date())
    assert [(r["o"], r["h"], r["l"], r["c"]) for r in rows] == [(10, 12, 9, 11.5), (12, 14, 11, 13.5)]


def test_alpaca_timeframe_from_decisions(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    tf = engine._velez_alpaca_timeframe
    assert [tf(v) for v in ("15", "5m", "60", "240", "1h", "D", "1Day", "15Min", "", None, "W")] == [
        "15Min", "5Min", "1Hour", "4Hour", "1Hour", "1Day", "1Day", "15Min", None, None, None]


def test_equity_daily_bar_is_complete_at_the_bell(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    bar = Bar(timestamp=datetime(2026, 6, 3, tzinfo=timezone.utc), open=1, high=1, low=1, close=1, volume=1)
    assert engine._velez_bar_end(bar, "1Day", True) == datetime(2026, 6, 3, 20, 0, tzinfo=timezone.utc)
    assert engine._velez_bar_end(bar, "1Day", False) == datetime(2026, 6, 4, tzinfo=timezone.utc)
    assert engine._velez_bar_end(bar, "15Min", True) == datetime(2026, 6, 3, 0, 15, tzinfo=timezone.utc)


def test_entry_time_is_the_opening_fill_not_the_decision(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    decided = datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc)
    pos = position(0.5)
    pos["linked_decision"]["timestamp"] = decided.isoformat()
    pos["entry_fill"] = {"side": "buy", "transaction_time": (decided + timedelta(minutes=40)).isoformat()}
    assert engine._velez_entry_time(pos) == decided + timedelta(minutes=40)
    pos.pop("entry_fill")
    assert engine._velez_entry_time(pos) == decided


def test_opening_fill_ignores_adds_exits_and_older_trades(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    decided = datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc)
    at = lambda minutes: (decided + timedelta(minutes=minutes)).isoformat()
    fills = [  # newest first, as the lifecycle reads them
        {"symbol": "SPY", "side": "sell", "transaction_time": at(200)},   # a partial exit
        {"symbol": "SPY", "side": "buy", "transaction_time": at(120)},    # a pyramid add
        {"symbol": "SPY", "side": "buy", "transaction_time": at(31)},     # second piece of a split fill
        {"symbol": "SPY", "side": "buy", "transaction_time": at(30)},     # the opening fill
        {"symbol": "QQQ", "side": "buy", "transaction_time": at(10)},
        {"symbol": "SPY", "side": "buy", "transaction_time": at(-600)},   # a previous trade
    ]
    opening = engine._velez_opening_fill("SPY", True, {"timestamp": decided.isoformat()}, fills)
    assert opening["transaction_time"] == at(30)
    short = engine._velez_opening_fill("SPY", False, {"timestamp": decided.isoformat()}, fills)
    assert short["transaction_time"] == at(200)


def test_verdict_reads_bars_on_the_decision_timeframe(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    engine.scanner_config["timeframe"] = "1Hour"
    seen = []
    monkeypatch.setattr(engine, "_fetch_scanner_bars", lambda symbol, asset_type, timeframe=None: seen.append(timeframe) or [])
    pos = position(0.5)
    pos["linked_decision"]["timeframe"] = "15"
    engine._velez_profit_taking_verdict(pos)
    pos["linked_decision"].pop("timeframe")
    engine._velez_profit_taking_verdict(pos)
    assert seen == ["15Min", "1Hour"]


def test_first_partial_still_eligible_past_second_r(monkeypatch, tmp_path):
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    monkeypatch.setattr(engine, "_velez_profit_taking_verdict", lambda p: {"status": "take_partial"})
    actions = engine._auto_lifecycle_actions(positions=[position(2.4)], open_orders=[], guardrails=[])
    assert [a["action"] for a in actions if a["action"].startswith("partial_")] == ["partial_first_r"]
    assert [o["qty"] for o in partial_orders(broker)] == ["50"]
    # The 2R partial follows on the next pass.
    engine._auto_lifecycle_actions(positions=[position(2.4)], open_orders=[], guardrails=[])
    assert [o["client_order_id"].split("-")[2] for o in partial_orders(broker)] == ["1r", "2r"]


def test_non_equity_daily_atr_comes_from_its_own_bars(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    engine.symbol_config["BTC/USD"] = {"symbol": "BTC/USD", "type": "crypto"}
    engine.scanner_config["timeframe"] = "1Day"
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    # 20 quiet days (true range 2.0), then three pushes that end 5 ATRs above the hold's low.
    closes = [100.0] * 20 + [101, 103, 102.5, 105, 104.5, 110]
    bars = [Bar(timestamp=today - timedelta(days=len(closes) + 1 - i), open=c, high=c + 1, low=c - 1, close=c, volume=1)
            for i, c in enumerate(closes)]
    monkeypatch.setattr(engine, "_fetch_scanner_bars", lambda symbol, asset_type, timeframe=None: bars)
    monkeypatch.setattr(engine, "_velez_daily_rows", lambda symbol: (_ for _ in ()).throw(AssertionError("equities only")))
    pos = position(0.8)
    pos["symbol"] = "BTC/USD"
    pos["linked_decision"]["timestamp"] = (bars[20].timestamp + timedelta(hours=1)).isoformat()
    verdict = engine._velez_profit_taking_verdict(pos)
    assert verdict["daily_atr"] is not None
    assert verdict["status"] == "take_profits"


def test_broker_crypto_alias_reads_crypto_bars(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    engine.symbol_config["BTC/USD"] = {"symbol": "BTC/USD", "type": "crypto"}
    seen = []
    monkeypatch.setattr(engine, "_fetch_scanner_bars",
                        lambda symbol, asset_type, timeframe=None: seen.append(asset_type) or [])
    pos = position(0.5)
    pos["symbol"] = "BTCUSD"  # how the broker reports the configured BTC/USD
    engine._velez_profit_taking_verdict(pos)
    assert seen == ["crypto"]


def test_session_feed_keeps_the_open_when_local_bars_rolled_it_out():
    strat = strategy(daily_range=True)
    strat.daily_bars_provider = lambda symbol: daily_rows()
    # The local window only holds the afternoon; the session feed still has the 99.0 opening low.
    ctx = strat._get_context("SPY")
    for b in (hour_bar(13, 100.6, 100.9, 100.5, 100.8),):
        ctx.bars.append(Bar(timestamp=b["t"], open=b["o"], high=b["h"], low=b["l"], close=b["c"], volume=1))
    strat.session_bars_provider = lambda symbol: [hour_bar(9, 100, 100.5, 99.0, 100.2), hour_bar(13, 100.6, 100.9, 100.5, 100.8)]
    bar = Bar(timestamp=hour_bar(14, 0, 0, 0, 0)["t"], open=100.8, high=101.2, low=100.7, close=101.1, volume=1)
    assert abs(strat._range_used(signal(), bar) - 1.05) < 1e-9


def test_bare_alert_gets_the_daily_range_veto():
    strat = strategy(daily_range=True)
    strat.daily_bars_provider = lambda symbol: daily_rows()
    strat.session_bars_provider = lambda symbol: [hour_bar(9, 100, 100.5, 99.0, 100.2), hour_bar(10, 100.2, 101.5, 100.1, 101.4)]
    at = hour_bar(11, 0, 0, 0, 0)["t"]
    # No chart context: price is the feed's latest close (101.4), 1.2 daily ATRs up from 99.0.
    gate = strat._context_free_gate(signal(), at)
    assert gate["allowed"] is False and "daily_range_exhausted" in gate["reasons"]
    strat.session_bars_provider = lambda symbol: []
    assert strat._context_free_gate(signal(), at)["allowed"] is True  # nothing to measure: not enforced


def test_futures_bars_follow_the_decision_timeframe(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    seen = []
    monkeypatch.setattr(engine, "_fetch_polygon_futures_bars", lambda symbol, timeframe=None: seen.append(timeframe) or [])
    engine._fetch_scanner_bars(symbol="ESZ6", asset_type="futures", timeframe="15Min")
    engine._fetch_scanner_bars(symbol="ESZ6", asset_type="futures")
    assert seen == ["15Min", None]


def test_intraday_crypto_reads_daily_bars_for_its_atrs(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    engine.symbol_config["BTC/USD"] = {"symbol": "BTC/USD", "type": "crypto"}
    engine.scanner_config["timeframe"] = "15Min"
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=3)
    intraday = [Bar(timestamp=start + timedelta(minutes=15 * i), open=100 + i, high=101 + i, low=99.5 + i, close=100.5 + i,
                    volume=1) for i in range(6)]
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    daily = [Bar(timestamp=today - timedelta(days=70 - i), open=100, high=101, low=99, close=100, volume=1) for i in range(70)]
    asked = []

    def fetch(symbol, asset_type, timeframe=None):
        asked.append(timeframe)
        return daily if timeframe == "1Day" else intraday

    monkeypatch.setattr(engine, "_fetch_scanner_bars", fetch)
    pos = position(0.5)
    pos["symbol"] = "BTC/USD"
    pos["linked_decision"]["timestamp"] = (start + timedelta(minutes=5)).isoformat()
    verdict = engine._velez_profit_taking_verdict(pos)
    assert "1Day" in asked
    assert verdict["daily_atr"] == 2.0 and verdict["wide_day_atr"] == 2.0
