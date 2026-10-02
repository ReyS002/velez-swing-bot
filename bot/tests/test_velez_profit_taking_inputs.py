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
    t0 = datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc)
    at = lambda minutes: (t0 + timedelta(minutes=minutes)).isoformat()
    fills = [  # newest first, as the lifecycle reads them
        {"symbol": "SPY", "side": "sell", "qty": "30", "transaction_time": at(200)},   # a partial exit
        {"symbol": "SPY", "side": "buy", "qty": "20", "transaction_time": at(120)},    # a pyramid add
        {"symbol": "SPY", "side": "buy", "qty": "40", "transaction_time": at(31)},     # second piece of a split fill
        {"symbol": "SPY", "side": "buy", "qty": "60", "transaction_time": at(30)},     # the opening fill
        {"symbol": "QQQ", "side": "buy", "qty": "10", "transaction_time": at(10)},
        {"symbol": "SPY", "side": "sell", "qty": "50", "transaction_time": at(-300)},  # a previous trade, closed
        {"symbol": "SPY", "side": "buy", "qty": "50", "transaction_time": at(-600)},
    ]
    # Whatever decision the lifecycle linked (here the add's), the open is found from the fills.
    linked_to_add = {"timestamp": at(119)}
    opening = engine._velez_opening_fill("SPY", True, linked_to_add, fills, 90)
    assert opening["transaction_time"] == at(30)
    # A window that starts mid-trade can't see the open: no answer rather than a wrong one.
    assert engine._velez_opening_fill("SPY", True, linked_to_add, fills[:3], 90) is None
    assert engine._velez_opening_fill("SPY", True, linked_to_add, fills, 75) is None


def test_short_opening_fill(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    t0 = datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc)
    at = lambda minutes: (t0 + timedelta(minutes=minutes)).isoformat()
    fills = [{"symbol": "SPY", "side": "sell_short", "qty": "10", "transaction_time": at(40)},
             {"symbol": "SPY", "side": "sell", "qty": "10", "transaction_time": at(5)}]
    assert engine._velez_opening_fill("SPY", False, None, fills, 20)["transaction_time"] == at(5)


def test_pushes_not_counted_when_history_starts_after_entry(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    engine.scanner_config["timeframe"] = "15Min"
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=3)
    prices = [(100, 101, 99.5, 100.8), (100.8, 101.5, 100.5, 101.2), (101.2, 101.3, 100.9, 101.0),
              (101.0, 102.0, 100.9, 101.8), (101.8, 101.9, 101.4, 101.5), (101.5, 102.6, 101.4, 102.4)]
    bars = [Bar(timestamp=start + timedelta(minutes=15 * i), open=o, high=h, low=l, close=c, volume=1)
            for i, (o, h, l, c) in enumerate(prices)]
    monkeypatch.setattr(engine, "_fetch_scanner_bars", lambda symbol, asset_type, timeframe=None: bars)
    monkeypatch.setattr(engine, "_velez_daily_rows", lambda symbol: daily_rows(70, last_day=now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)))
    pos = position(0.5)
    pos["linked_decision"]["timestamp"] = (start - timedelta(days=2)).isoformat()  # entered long before the window
    # Earlier pushes and the move's origin are out of view: unreadable, so the R-multiple partial applies.
    assert engine._velez_profit_taking_verdict(pos) is None


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


def test_r_after_breakeven_uses_the_initial_stop(monkeypatch, tmp_path):
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    monkeypatch.setattr(engine, "_velez_profit_taking_verdict", lambda p: {"status": "take_partial"})
    pos = position(None)
    pos.update(stop_price=500.0, current_price=503.0)  # stop already at entry: current R undefined
    assert engine._velez_initial_r(pos) == 0.6  # (503 - 500) / (500 - 495)
    engine._auto_lifecycle_actions(positions=[pos], open_orders=[], guardrails=[])
    assert [o["qty"] for o in partial_orders(broker)] == ["50"]


def test_partial_quantities_never_round_up(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    engine.symbol_config["BTC/USD"] = {"symbol": "BTC/USD", "type": "crypto"}
    qty = lambda symbol, held, pct: engine._velez_partial_qty({"symbol": symbol, "qty": held}, pct)
    assert qty("SPY", "100", 0.5) == 50
    assert qty("SPY", "3", 0.5) == 1
    assert qty("SPY", "1", 0.5) == 0  # one share: no partial, the whole position rides
    assert qty("BTC/USD", "0.1", 0.5) == 0.05
    assert qty("BTCUSD", "0.00000001", 0.5) == 0


def test_forex_has_no_verdict_so_the_r_partial_applies(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    engine.symbol_config["EUR/USD"] = {"symbol": "EUR/USD", "type": "forex"}
    monkeypatch.setattr(engine, "_fetch_scanner_bars", lambda **kw: (_ for _ in ()).throw(AssertionError("no forex feed")))
    pos = position(0.5)
    pos["symbol"] = "EUR/USD"
    assert engine._velez_profit_taking_verdict(pos) is None


def test_position_links_to_its_decision_through_an_alias(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    decisions = [{"symbol": "BTC/USD", "side": "buy", "status": "submitted", "timestamp": "2026-06-03T14:00:00+00:00"}]
    assert engine._link_decision_for_symbol("BTCUSD", decisions, side="long") == decisions[0]
    assert engine._link_decision_for_symbol("ETHUSD", decisions, side="long") is None


def test_bare_alert_is_measured_at_its_entry_price():
    strat = strategy(daily_range=True)
    strat.daily_bars_provider = lambda symbol: daily_rows()
    strat.session_bars_provider = lambda symbol: [hour_bar(9, 100, 100.5, 99.0, 100.2), hour_bar(10, 100.2, 100.9, 100.1, 100.8)]
    at = hour_bar(11, 0, 0, 0, 0)["t"]
    cached = Bar(timestamp=hour_bar(10, 0, 0, 0, 0)["t"], open=100.2, high=100.9, low=100.1, close=100.8, volume=1)
    alert = signal()
    alert.metadata["entry_price"] = 101.4  # price moved after the last scanner bar
    assert abs(strat._range_used(alert, cached, decision_at=at) - 1.2) < 1e-9
    assert abs(strat._range_used(signal(), cached, decision_at=at) - 0.9) < 1e-9


def test_split_adjusted_history_keeps_a_real_big_gap():
    from bot.core.velez_strategy import daily_atr_from_rows, split_safe_daily_rows
    rows = daily_rows(20)
    rows[12:] = [{**r, "o": r["o"] * 1.4, "h": r["h"] * 1.4, "l": r["l"] * 1.4, "c": r["c"] * 1.4} for r in rows[12:]]
    assert split_safe_daily_rows(rows) == rows[12:]  # raw feed: treated as a split
    adjusted = [{**r, "split_adjusted": True} for r in rows]
    assert split_safe_daily_rows(adjusted) == adjusted  # adjusted feed: a 40% gap is a real move
    assert daily_atr_from_rows(adjusted) is not None


def test_round_the_clock_rows_are_never_split_guarded():
    t0 = datetime(2026, 5, 1, tzinfo=timezone.utc)
    bars = [{"o": 100.0, "h": 101.0, "l": 99.0, "c": 100.0, "v": 1, "t": t0 + timedelta(days=i)} for i in range(20)]
    bars[10] = {**bars[10], "o": 140.0, "h": 141.0, "l": 139.0, "c": 140.0}
    rows = utc_daily_rows(bars, before=datetime(2026, 6, 1, tzinfo=timezone.utc).date())
    assert all(r["split_adjusted"] for r in rows)


def test_bare_alert_without_a_price_uses_the_freshest_feed_close():
    strat = strategy(daily_range=True)
    strat.daily_bars_provider = lambda symbol: daily_rows()
    ctx = strat._get_context("SPY")
    stale = hour_bar(9, 100, 100.5, 99.0, 100.2)
    ctx.bars.append(Bar(timestamp=stale["t"], open=100, high=100.5, low=99.0, close=100.2, volume=1))
    # The feed has moved on to 101.6 since the cached hourly bar closed.
    strat.session_bars_provider = lambda symbol: [stale, hour_bar(10, 100.2, 101.7, 100.1, 101.6)]
    cached = ctx.bars[-1]
    used = strat._range_used(signal(), cached, decision_at=hour_bar(11, 0, 0, 0, 0)["t"])
    assert abs(used - 1.3) < 1e-9  # (101.6 - 99.0) / 2.0, not the stale 100.2


def test_profit_taking_origin_uses_the_full_session_feed(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    engine.scanner_config["timeframe"] = "15Min"
    # Wed 2026-06-03 (EDT): bars from 11:00 ET; the rolling window no longer holds the morning.
    start = datetime(2026, 6, 3, 15, 0, tzinfo=timezone.utc)
    prices = [(101, 101.5, 100.8, 101.2), (101.2, 101.6, 101.0, 101.4), (101.4, 101.9, 101.2, 101.8)]
    bars = [Bar(timestamp=start + timedelta(minutes=15 * i), open=o, high=h, low=l, close=c, volume=1)
            for i, (o, h, l, c) in enumerate(prices)]
    monkeypatch.setattr(engine, "_fetch_scanner_bars", lambda symbol, asset_type, timeframe=None: bars)
    monkeypatch.setattr(engine, "_velez_daily_rows", lambda symbol: daily_rows(70))
    # The 09:40 ET low (99.6) is only in the full-session feed.
    morning = {"o": 100.0, "h": 100.2, "l": 99.6, "c": 100.1, "v": 1, "t": datetime(2026, 6, 3, 13, 40, tzinfo=timezone.utc)}
    monkeypatch.setattr(engine, "_velez_session_bars", lambda symbol, since_day=None: [morning])
    pos = position(0.5)
    pos["linked_decision"]["timestamp"] = (start + timedelta(minutes=5)).isoformat()
    verdict = engine._velez_profit_taking_verdict(pos)
    assert verdict["origin"] == 99.6
    assert verdict["move_from_origin"] == 2.2


def test_r_fallback_first_partial_is_eligible_past_second_r(monkeypatch, tmp_path):
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    monkeypatch.setattr(engine, "_velez_profit_taking_verdict", lambda p: None)  # e.g. forex: no feed
    engine._auto_lifecycle_actions(positions=[position(2.4)], open_orders=[], guardrails=[])
    engine._auto_lifecycle_actions(positions=[position(2.4)], open_orders=[], guardrails=[])
    assert [o["client_order_id"].split("-")[2] for o in partial_orders(broker)] == ["1r", "2r"]


def test_initial_risk_is_recorded_once_per_position(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    opening = {"side": "buy", "transaction_time": "2026-06-03T14:30:00+00:00"}
    first = position(0.4)
    first.update(entry_fill=opening, stop_price=495.0, current_price=502.0)  # risk 5.0
    engine._velez_record_initial_risk(first)
    # Later: a pyramid add (its decision has a tighter stop), and the stop is at breakeven.
    later = position(None)
    later.update(entry_fill=opening, stop_price=500.0, current_price=505.0)
    later["linked_decision"]["stop_price"] = 503.0
    engine._velez_record_initial_risk(later)  # breakeven stop: nothing new recorded
    assert engine._velez_initial_r(later) == 1.0  # (505 - 500) / 5.0, not / 3.0 from the add
    # A new position (a different opening fill) gets its own risk.
    fresh = position(0.2)
    fresh.update(entry_fill={"side": "buy", "transaction_time": "2026-06-04T14:30:00+00:00"}, stop_price=498.0)
    engine._velez_record_initial_risk(fresh)
    assert engine._velez_position_key(fresh) != engine._velez_position_key(first)


def test_opening_fill_tracks_signed_inventory_across_directions(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    t0 = datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc)
    at = lambda minutes: (t0 + timedelta(minutes=minutes)).isoformat()
    # A closed long (buy 50, sell 50), then the current short: its closing sell is not an entry.
    fills = [{"symbol": "SPY", "side": "sell", "qty": "20", "transaction_time": at(60)},
             {"symbol": "SPY", "side": "sell", "qty": "50", "transaction_time": at(30)},
             {"symbol": "SPY", "side": "buy", "qty": "50", "transaction_time": at(0)}]
    assert engine._velez_opening_fill("SPY", False, None, fills, 20)["transaction_time"] == at(60)
    # One fill that flips a long into a short opens the short.
    flip = [{"symbol": "SPY", "side": "sell", "qty": "70", "transaction_time": at(30)},
            {"symbol": "SPY", "side": "buy", "qty": "50", "transaction_time": at(0)}]
    assert engine._velez_opening_fill("SPY", False, None, flip, 20)["transaction_time"] == at(30)
    assert engine._velez_opening_fill("SPY", True, None, flip, 20) is None  # we're short, not long


def test_lifecycle_finds_the_opening_fill_of_a_fractional_position(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    item = {"symbol": "BTCUSD", "qty": "0.1", "side": "long", "avg_entry_price": "60000.5", "current_price": "60500.25"}
    fills = [{"symbol": "BTCUSD", "side": "buy", "qty": "0.1", "transaction_time": "2026-06-03T14:00:00+00:00"}]
    built = engine._position_lifecycle(item, decisions=[], orders=[], fills=fills)
    assert built["entry_fill"]["transaction_time"] == fills[0]["transaction_time"]  # 0.1 held, not truncated to 0
    assert built["velez_entry_price"] == 60000.5 and built["velez_current_price"] == 60500.25


def test_entry_time_is_the_opening_fill_even_when_an_add_is_linked(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    opened = datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc)
    pos = position(0.5)
    pos["linked_decision"]["timestamp"] = (opened + timedelta(hours=2)).isoformat()  # the add's decision
    pos["entry_fill"] = {"side": "buy", "transaction_time": opened.isoformat()}
    assert engine._velez_entry_time(pos) == opened


def test_partial_r_uses_the_initial_risk_once_the_stop_trails(monkeypatch, tmp_path):
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    monkeypatch.setattr(engine, "_velez_profit_taking_verdict", lambda p: {"status": "hold"})
    opening = {"side": "buy", "transaction_time": "2026-06-03T14:30:00+00:00"}
    first = position(0.2)
    first.update(entry_fill=opening, current_price=501.0)
    engine._velez_record_initial_risk(first)  # risk 5.0
    # Later the stop trails to 500.10: current R reads 60, the trade is really 1.2R.
    trailed = position(60.0)
    trailed.update(entry_fill=opening, stop_price=500.10, current_price=506.0)
    assert abs(engine._velez_initial_r(trailed) - 1.2) < 1e-9
    engine._auto_lifecycle_actions(positions=[trailed], open_orders=[], guardrails=[])
    assert partial_orders(broker) == []  # neither the 2R partial nor the first (verdict: hold)


def test_recorded_risk_outlives_the_fill_lookback(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    first = position(0.2)
    first.update(entry_fill={"side": "buy", "transaction_time": "2026-05-20T14:30:00+00:00"}, current_price=501.0)
    engine._velez_record_initial_risk(first)  # risk 5.0
    # Weeks later the opening fill is out of the fill snapshot, the stop is at entry, and the
    # linked decision is an add with a tighter stop.
    aged = position(None)
    aged.update(stop_price=500.0, current_price=505.0)
    aged["linked_decision"]["stop_price"] = 503.0
    assert engine._velez_initial_r(aged) == 1.0  # / 5.0 recorded, not / 3.0
    aged["side"] = "short"  # a different position on the other side doesn't inherit it
    assert engine._velez_recorded_risk(aged) is None


def test_recorded_risk_keeps_sub_cent_precision(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    pos = {"symbol": "ADAUSD", "qty": "1000", "side": "long", "entry_price": 0.51, "stop_price": 0.51,
           "current_price": 0.52, "velez_entry_price": 0.51234, "velez_stop_price": 0.50734,
           "velez_current_price": 0.52234, "entry_fill": {"side": "buy", "transaction_time": "2026-06-03T14:30:00+00:00"},
           "linked_decision": {}}
    engine._velez_record_initial_risk(pos)
    assert abs(engine._velez_recorded_risk(pos) - 0.005) < 1e-12
    assert abs(engine._velez_initial_r(pos) - 2.0) < 1e-9


def test_configured_non_equity_aliases_skip_equity_rules():
    strat = strategy(daily_range=True, non_equity_symbols=["EUR/USD", "BTC/USD"])
    assert strat._is_equity("EURUSD") is False and strat._is_equity("BTCUSD") is False
    assert strat._is_equity("SPY") is True


def test_alias_claim_links_after_the_decision_leaves_the_window(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    decision = {"symbol": "BTC/USD", "side": "buy", "status": "submitted", "alert_ref": "a1",
                "timestamp": "2026-06-03T14:00:00+00:00"}
    engine._set_lifecycle_claim("BTC/USD", decision)
    monkeypatch.setattr(engine.journal, "decision_by_alert_ref", lambda ref: decision if ref == "a1" else None)
    # The decision is no longer in the recent list, but the claim (stored as BTC/USD) still links BTCUSD.
    assert engine._link_decision_for_symbol("BTCUSD", [], side="long") == decision
    assert engine._claim_candidates_for_symbol("BTCUSD", [decision], side="long") == [decision]


def test_session_feed_is_full_tape_first(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    monkeypatch.setattr(engine.broker, "is_configured", lambda: True, raising=False)
    import bot.webhook_server as ws
    now = datetime(2026, 6, 3, 15, 0, tzinfo=timezone.utc)  # 11:00 ET, in the session
    monkeypatch.setattr(ws, "datetime", type("FrozenDatetime", (datetime,), {"now": staticmethod(lambda tz=None: now if tz is None else now.astimezone(tz))}))
    t = lambda minutes: (now - timedelta(minutes=minutes)).isoformat()
    feeds = []

    def data(path, params):
        feeds.append(params["feed"])
        if params["feed"] == "sip":  # delayed 15 minutes, but the true low
            return {"bars": {"SPY": [{"t": t(40), "o": 100, "h": 101, "l": 98.5, "c": 100.5, "v": 1}]}}
        return {"bars": {"SPY": [{"t": t(40), "o": 100, "h": 101, "l": 99.5, "c": 100.5, "v": 1},
                                 {"t": t(5), "o": 100.5, "h": 101.5, "l": 100.4, "c": 101.2, "v": 1}]}}

    monkeypatch.setattr(engine, "_alpaca_data_request", data)
    rows = engine._velez_session_bars("SPY")
    assert feeds[0] == "sip"
    assert [r["l"] for r in rows] == [98.5, 100.4]  # SIP's bar where both have one, the feed's latest after


def test_daily_fallback_is_split_adjusted(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    monkeypatch.setattr(engine.broker, "is_configured", lambda: True, raising=False)
    asked = []

    def data(path, params):
        asked.append((params["feed"], params["adjustment"]))
        if params["feed"] == "sip":
            raise RuntimeError("no sip")
        return {"bars": [{"t": "2026-06-01T04:00:00Z", "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 1}]}

    monkeypatch.setattr(engine, "_alpaca_data_request", data)
    rows = engine._velez_daily_rows("SPY")
    assert asked == [("sip", "split"), ("iex", "split")] and all(r["split_adjusted"] for r in rows)


def _two_day_hold(monkeypatch, engine, yesterday_prices, today_prices, adjusted_yesterday_close):
    """15-minute bars: yesterday's afternoon (the entry) and this morning, with split-adjusted daily rows."""
    engine.scanner_config["timeframe"] = "15Min"
    # Thu 2026-06-04 entry, Fri 2026-06-05 today (EDT): 18:00 UTC = 14:00 ET.
    y0 = datetime(2026, 6, 4, 18, 0, tzinfo=timezone.utc)
    t0 = datetime(2026, 6, 5, 14, 0, tzinfo=timezone.utc)
    bars = [Bar(timestamp=y0 + timedelta(minutes=15 * i), open=o, high=h, low=l, close=c, volume=1)
            for i, (o, h, l, c) in enumerate(yesterday_prices)]
    bars += [Bar(timestamp=t0 + timedelta(minutes=15 * i), open=o, high=h, low=l, close=c, volume=1)
             for i, (o, h, l, c) in enumerate(today_prices)]
    rows = [{**r, "split_adjusted": True} for r in daily_rows(70, last_day=datetime(2026, 6, 4, tzinfo=timezone.utc))]
    rows[-1]["c"] = adjusted_yesterday_close
    monkeypatch.setattr(engine, "_fetch_scanner_bars", lambda symbol, asset_type, timeframe=None: bars)
    monkeypatch.setattr(engine, "_velez_daily_rows", lambda symbol: rows)
    monkeypatch.setattr(engine, "_velez_session_bars", lambda symbol, since_day=None: [])
    import bot.webhook_server as ws
    monkeypatch.setattr(ws, "datetime", type("FrozenDatetime", (datetime,), {"now": staticmethod(lambda tz=None: datetime(2026, 6, 5, 16, 0, tzinfo=timezone.utc))}))
    pos = position(0.5)
    pos["linked_decision"]["timestamp"] = (y0 + timedelta(minutes=1)).isoformat()  # filled in the first bar
    return pos


def test_split_inside_the_hold_falls_back_to_the_r_partial(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    # 2-for-1 overnight: yesterday's raw 200s are 100s on the adjusted daily series.
    pos = _two_day_hold(monkeypatch, engine, [(200, 201, 199, 200.5), (200.5, 201.5, 200, 201)],
                        [(100.5, 101, 100, 100.8), (100.8, 101.4, 100.6, 101.2)], adjusted_yesterday_close=100.5)
    assert engine._velez_profit_taking_verdict(pos) is None


def test_a_real_big_gap_is_not_a_split(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    # A 40% earnings gap: the raw closes match the adjusted daily close, so the verdict is read.
    pos = _two_day_hold(monkeypatch, engine, [(100, 101, 99.5, 100.5), (100.5, 101, 100, 100.8)],
                        [(140, 141, 139.5, 140.8), (140.8, 141.4, 140.6, 141.2)], adjusted_yesterday_close=100.8)
    assert engine._velez_profit_taking_verdict(pos) is not None


def test_first_record_uses_the_journaled_stop_when_the_stop_already_trailed(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    # First seen after a restart: the broker stop has trailed to 500.10, the journal still has 495.
    opening = {"symbol": "SPY", "side": "buy", "status": "submitted", "stop_price": 495.0,
               "timestamp": "2026-06-03T14:29:00+00:00"}
    monkeypatch.setattr(engine.journal, "decision_entries", lambda limit=80, **kw: [opening])
    pos = position(60.0)
    pos.update(entry_fill={"side": "buy", "transaction_time": "2026-06-03T14:30:00+00:00"},
               stop_price=500.10, current_price=506.0)
    engine._velez_record_initial_risk(pos)
    assert engine._velez_recorded_risk(pos) == 5.0
    assert abs(engine._velez_initial_r(pos) - 1.2) < 1e-9


def test_verdict_keeps_the_opening_timeframe_after_an_add(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    opening = {"side": "buy", "transaction_time": "2026-06-03T14:30:00+00:00"}
    decisions = [{"symbol": "SPY", "side": "buy", "status": "submitted", "stop_price": 495.0, "timeframe": "60",
                  "timestamp": "2026-06-03T17:00:00+00:00"},
                 {"symbol": "SPY", "side": "buy", "status": "submitted", "stop_price": 495.0, "timeframe": "15",
                  "timestamp": "2026-06-03T14:29:00+00:00"}]
    monkeypatch.setattr(engine.journal, "decision_entries", lambda limit=80, **kw: decisions)
    first = position(0.3)
    first.update(entry_fill=opening)
    first["linked_decision"]["timeframe"] = "15"
    engine._velez_record_initial_risk(first)
    later = position(0.8)
    later.update(entry_fill=opening)
    later["linked_decision"]["timeframe"] = "60"  # the add came from the hourly chart
    engine._velez_record_initial_risk(later)
    seen = []
    monkeypatch.setattr(engine, "_fetch_scanner_bars", lambda symbol, asset_type, timeframe=None: seen.append(timeframe) or [])
    engine._velez_profit_taking_verdict(later)
    assert seen == ["15Min"]


def test_multi_day_equity_bars_leave_it_to_the_r_partial(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    monkeypatch.setattr(engine, "_fetch_scanner_bars", lambda **kw: (_ for _ in ()).throw(AssertionError("no fetch")))
    pos = position(0.5)
    pos["linked_decision"]["timeframe"] = "2D"
    assert engine._velez_profit_taking_verdict(pos) is None


def test_range_is_measured_at_the_planned_entry():
    strat = strategy(daily_range=True)
    strat.daily_bars_provider = lambda symbol: daily_rows()
    strat.session_bars_provider = lambda symbol: [hour_bar(9, 100, 100.5, 99.0, 100.2), hour_bar(10, 100.2, 101.8, 100.1, 101.6)]
    spike = Bar(timestamp=hour_bar(10, 0, 0, 0, 0)["t"], open=100.2, high=101.8, low=100.1, close=101.6, volume=1)
    assert abs(strat._range_used(signal(), spike) - 1.3) < 1e-9  # at the close
    assert abs(strat._range_used(signal(), spike, entry_at=100.8) - 0.9) < 1e-9  # at the limit


def test_armed_runaway_break_is_gated_at_its_limit(monkeypatch):
    strat = strategy(daily_range=True)
    seen = {}

    def gate(original, bar, location, market, event_open=None, decision_at=None, entry_at=None):
        seen["entry_at"] = entry_at
        return {"allowed": False, "reasons": ["test"]}

    monkeypatch.setattr(strat, "_doctrine_gate", gate)
    ctx = strat._get_context("SPY")
    original = signal()
    original.metadata["stop_price"] = 98.0
    ctx.armed["long"] = {"signal": original, "trigger": 100.0, "bars_left": 3, "event_open": 99.0,
                         "event_high": 100.0, "event_low": 99.0, "armed_at": hour_bar(9, 0, 0, 0, 0)["t"]}
    runaway = Bar(timestamp=hour_bar(10, 0, 0, 0, 0)["t"], open=100.0, high=103.2, low=99.9, close=103.0, volume=1)
    strat._fire_armed("SPY", runaway, ctx, None, {}, 0.5)
    assert seen["entry_at"] == 100.0  # the limit at the breakout level, not the 103 close


def test_one_completed_entry_bar_is_measured_against_the_atrs(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    engine.scanner_config["timeframe"] = "15Min"
    start = datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc)  # 10:00 ET, in the session
    entry_bar = Bar(timestamp=start, open=100, high=103, low=99.8, close=102.8, volume=1)
    monkeypatch.setattr(engine, "_fetch_scanner_bars", lambda symbol, asset_type, timeframe=None: [entry_bar])
    monkeypatch.setattr(engine, "_velez_daily_rows", lambda symbol: daily_rows(70))
    monkeypatch.setattr(engine, "_velez_session_bars", lambda symbol, since_day=None: [])
    pos = position(0.5)
    pos["linked_decision"]["timestamp"] = (start + timedelta(minutes=1)).isoformat()  # filled in the bar
    verdict = engine._velez_profit_taking_verdict(pos)
    assert verdict is not None and verdict["pushes"] == 0 and verdict["daily_atr"] == 2.0


def test_entry_time_outlives_the_fill_lookback(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    opened = "2026-05-20T14:30:00+00:00"
    first = position(0.2)
    first.update(entry_fill={"side": "buy", "transaction_time": opened})
    engine._velez_record_initial_risk(first)
    aged = position(0.6)
    aged["linked_decision"]["timestamp"] = "2026-05-27T15:00:00+00:00"  # an add, still in the window
    assert engine._velez_entry_time(aged) == datetime(2026, 5, 20, 14, 30, tzinfo=timezone.utc)


def test_second_partial_waits_for_the_first_to_fill(monkeypatch, tmp_path):
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    monkeypatch.setattr(engine, "_velez_profit_taking_verdict", lambda p: {"status": "take_partial"})
    engine._auto_lifecycle_actions(positions=[position(2.4)], open_orders=[], guardrails=[])
    first = partial_orders(broker)[0]
    pending = [{"symbol": "SPY", "client_order_id": first["client_order_id"], "status": "accepted"}]
    engine._auto_lifecycle_actions(positions=[position(2.4)], open_orders=pending, guardrails=[])
    assert len(partial_orders(broker)) == 1  # the 1R order is still open: no 2R order yet
    engine._auto_lifecycle_actions(positions=[position(2.4)], open_orders=[], guardrails=[])
    assert [o["client_order_id"].split("-")[2] for o in partial_orders(broker)] == ["1r", "2r"]


def test_profit_origin_keeps_the_full_tape_low(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    engine.scanner_config["timeframe"] = "15Min"
    start = datetime(2026, 6, 3, 13, 30, tzinfo=timezone.utc)
    prices = [(100, 100.4, 99.8, 100.2), (100.2, 101.0, 100.1, 100.9), (100.9, 101.8, 100.8, 101.7)]
    bars = [Bar(timestamp=start + timedelta(minutes=15 * i), open=o, high=h, low=l, close=c, volume=1)
            for i, (o, h, l, c) in enumerate(prices)]
    monkeypatch.setattr(engine, "_fetch_scanner_bars", lambda symbol, asset_type, timeframe=None: bars)
    monkeypatch.setattr(engine, "_velez_daily_rows", lambda symbol: daily_rows(70))
    # The same opening bar on the full tape printed 99.5, below IEX's 99.8.
    monkeypatch.setattr(engine, "_velez_session_bars", lambda symbol, since_day=None: [{"o": 100, "h": 100.4, "l": 99.5, "c": 100.2, "v": 1, "t": start}])
    pos = position(0.5)
    pos["linked_decision"]["timestamp"] = (start + timedelta(minutes=5)).isoformat()
    assert engine._velez_profit_taking_verdict(pos)["origin"] == 99.5


def test_midnight_utc_daily_bar_is_measured_on_its_own_date():
    strat = strategy(daily_range=True)
    strat.daily_bars_provider = lambda symbol: daily_rows()
    ctx = strat._get_context("SPY")
    for day in (1, 2):
        ctx.bars.append(Bar(timestamp=datetime(2026, 6, day, tzinfo=timezone.utc), open=100, high=101, low=99, close=100, volume=1))
    # Wed 2026-06-03 labelled 00:00 UTC (Tue evening in New York); the session feed is Wednesday's.
    strat.session_bars_provider = lambda symbol: [hour_bar(9, 100, 100.5, 99.0, 100.2), hour_bar(15, 100.2, 101.5, 100.1, 101.4)]
    bar = Bar(timestamp=datetime(2026, 6, 3, tzinfo=timezone.utc), open=100, high=101.5, low=99.0, close=101.4, volume=1)
    assert abs(strat._range_used(signal(), bar) - 1.2) < 1e-9


def test_recorded_risk_is_rebased_across_a_split(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    opening = {"side": "buy", "transaction_time": "2026-06-03T14:30:00+00:00"}
    first = position(0.2)
    first.update(entry_fill=opening, current_price=501.0)
    engine._velez_record_initial_risk(first)  # 100 @ 500, risk 5.0
    # 2-for-1: 200 shares @ 250, same cost basis. Stop at breakeven.
    after = position(None)
    after.update(entry_fill=opening, qty="200", entry_price=250.0, stop_price=250.0, current_price=253.0)
    engine._velez_record_initial_risk(after)
    assert abs(engine._velez_initial_r(after) - 1.2) < 1e-9  # 3 / 2.5, not 3 / 5


def test_a_flat_symbol_drops_its_record(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    first = position(0.2)
    first.update(entry_fill={"side": "buy", "transaction_time": "2026-05-20T14:30:00+00:00"}, current_price=501.0)
    engine._velez_record_initial_risk(first)
    engine._velez_prune_open_records({"QQQ"})  # SPY is no longer held
    reopened = position(0.3)  # a new SPY long whose opening fill isn't in the snapshot
    assert engine._velez_recorded_risk(reopened) is None
    engine._velez_prune_open_records(set())  # nothing left to clear


def test_risk_waits_for_the_entry_order_to_finish_filling(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    pos = position(0.2)
    pos.update(entry_fill={"side": "buy", "transaction_time": "2026-06-03T14:30:00+00:00"},
               open_orders=[{"symbol": "SPY", "side": "buy", "status": "partially_filled"}])
    engine._velez_record_initial_risk(pos)
    assert engine._velez_recorded_risk(pos) is None  # the average entry can still move
    pos.update(open_orders=[{"symbol": "SPY", "side": "sell", "status": "new", "type": "stop"}], entry_price=503.0)
    engine._velez_record_initial_risk(pos)
    assert engine._velez_recorded_risk(pos) == 8.0  # 503 to the 495 stop, once filled


def test_modest_forward_split_is_rebased_but_an_add_is_not(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    opening = {"side": "buy", "transaction_time": "2026-06-03T14:30:00+00:00"}
    first = position(0.2)
    first.update(entry_fill=opening, qty="30", entry_price=120.0, stop_price=108.0, current_price=121.0)
    first["linked_decision"]["stop_price"] = 108.0
    engine._velez_record_initial_risk(first)  # risk 12
    split = position(None)  # 4-for-3: 40 @ 90, same cost basis: risk 9
    split.update(entry_fill=opening, qty="40", entry_price=90.0, stop_price=90.0, current_price=99.0)
    engine._velez_record_initial_risk(split)
    assert abs(engine._velez_initial_r(split) - 1.0) < 1e-9
    added = position(None)  # a winner add: 60 @ 100 (the cost basis grows): no rebase
    added.update(entry_fill=opening, qty="60", entry_price=100.0, stop_price=100.0, current_price=109.0)
    engine._velez_record_initial_risk(added)
    assert abs(engine._velez_recorded_risk(added) - 9.0) < 1e-9


def test_keyless_position_rejects_a_recent_record(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    first = position(0.2)
    first.update(entry_fill={"side": "buy", "transaction_time": recent})
    engine._velez_record_initial_risk(first)
    # Same side, no opening fill in the snapshot, the record is recent, and the position isn't the one
    # last seen (another entry, no split): it may be another trade's. Not inherited.
    engine._velez_fills_complete = True  # an authoritative fill snapshot that doesn't show the open
    reopened = position(0.3)
    reopened.update(entry_price=505.0)
    assert engine._velez_open_record(reopened) is None
    assert engine._velez_open_record(position(0.3)) is not None  # the same position as last pass


def test_daily_rows_fall_back_to_yahoo_split_adjusted(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    monkeypatch.setattr(engine.broker, "is_configured", lambda: True, raising=False)
    monkeypatch.setattr(engine, "_alpaca_data_request", lambda path, params: (_ for _ in ()).throw(RuntimeError("down")))
    import pandas as pd
    import yfinance
    asked = {}

    def fake_download(ticker, **kwargs):
        asked.update(kwargs)
        index = pd.date_range("2026-03-02", periods=90, freq="B", tz="America/New_York")
        return pd.DataFrame({"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 1.0}, index=index)

    monkeypatch.setattr(yfinance, "download", fake_download)
    rows = engine._velez_daily_rows("SPY")
    assert asked["auto_adjust"] is False and asked["period"] == "9mo"  # split-adjusted, not dividend
    assert len(rows) == 90 and all(r["split_adjusted"] for r in rows)


def test_cold_start_after_an_add_uses_the_opening_decisions_stop(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    opening_decision = {"symbol": "SPY", "side": "buy", "status": "submitted", "stop_price": 95.0,
                        "timeframe": "15", "timestamp": "2026-06-03T14:29:00+00:00"}
    add_decision = {"symbol": "SPY", "side": "buy", "status": "submitted", "stop_price": 104.0,
                    "timeframe": "60", "timestamp": "2026-06-03T17:00:00+00:00"}
    monkeypatch.setattr(engine.journal, "decision_entries", lambda limit=80, **kw: [add_decision, opening_decision])
    pos = position(None)
    pos.update(entry_fill={"side": "buy", "price": "100", "transaction_time": "2026-06-03T14:30:00+00:00"},
               qty="150", entry_price=103.33, stop_price=100.0, current_price=110.0)
    pos["linked_decision"] = dict(add_decision)
    engine._velez_record_initial_risk(pos)
    assert engine._velez_recorded_risk(pos) == 5.0  # 100 fill to the 95 opening stop
    assert engine._velez_open_record(pos)["timeframe"] == "15"


def test_unsupported_decision_timeframe_leaves_the_verdict_unreadable(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    monkeypatch.setattr(engine, "_fetch_scanner_bars", lambda **kw: (_ for _ in ()).throw(AssertionError("no fetch")))
    pos = position(0.5)
    pos["linked_decision"]["timeframe"] = "1W"
    assert engine._velez_profit_taking_verdict(pos) is None


def test_a_recent_split_keeps_the_record_without_an_opening_fill(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    recent = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    first = position(0.2)
    first.update(entry_fill={"side": "buy", "transaction_time": recent}, current_price=501.0)
    engine._velez_record_initial_risk(first)  # 100 @ 500, risk 5
    # A 5-for-4 split: 125 @ 400. No fill, so the opening fill can't be rebuilt any more.
    after = position(None)
    after.update(qty="125", entry_price=400.0, stop_price=400.0, current_price=404.0)
    engine._velez_record_initial_risk(after)
    assert abs(engine._velez_recorded_risk(after) - 4.0) < 1e-9
    assert abs(engine._velez_initial_r(after) - 1.0) < 1e-9
    # The next pass sees the same position as last time: still accepted.
    engine._velez_record_initial_risk(after)
    assert engine._velez_open_record(after) is not None


def test_a_5_for_4_split_inside_the_hold_is_detected(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    pos = _two_day_hold(monkeypatch, engine, [(125, 126, 124, 125.5), (125.5, 126.5, 125, 126)],
                        [(100.5, 101, 100, 100.8), (100.8, 101.4, 100.6, 101.2)], adjusted_yesterday_close=100.8)
    assert engine._velez_profit_taking_verdict(pos) is None


def test_session_feed_keeps_the_pieces_of_the_last_closed_bar(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    engine.scanner_config["timeframe"] = "15Min"
    start = datetime(2026, 6, 3, 13, 30, tzinfo=timezone.utc)
    prices = [(101, 101.2, 100.6, 100.8), (100.8, 100.9, 100.2, 100.3), (100.3, 100.4, 99.6, 99.7)]
    bars = [Bar(timestamp=start + timedelta(minutes=15 * i), open=o, high=h, low=l, close=c, volume=1)
            for i, (o, h, l, c) in enumerate(prices)]
    monkeypatch.setattr(engine, "_fetch_scanner_bars", lambda symbol, asset_type, timeframe=None: bars)
    monkeypatch.setattr(engine, "_velez_daily_rows", lambda symbol: daily_rows(70))
    # The last closed bar starts 10:00 ET; the full tape's 10:10 piece spiked to 101.9, then made the low.
    piece = {"o": 100.0, "h": 101.9, "l": 99.5, "c": 99.6, "v": 1, "t": start + timedelta(minutes=40)}
    monkeypatch.setattr(engine, "_velez_session_bars", lambda symbol, since_day=None: [piece])
    pos = position(0.5)
    pos["side"] = "short"
    pos["linked_decision"]["timestamp"] = (start + timedelta(minutes=5)).isoformat()
    assert engine._velez_profit_taking_verdict(pos)["origin"] == 101.9


def test_a_pending_add_does_not_block_the_cold_start_risk(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    pos = position(0.2)
    pos.update(entry_fill={"side": "buy", "order_id": "open-1", "transaction_time": "2026-06-03T14:30:00+00:00"},
               open_orders=[{"id": "add-2", "symbol": "SPY", "side": "buy", "status": "new"}])
    engine._velez_record_initial_risk(pos)
    assert engine._velez_recorded_risk(pos) == 5.0
    pending = position(0.2)
    pending.update(entry_fill={"side": "buy", "order_id": "open-9", "transaction_time": "2026-06-04T14:30:00+00:00"},
                   open_orders=[{"id": "open-9", "symbol": "SPY", "side": "buy", "status": "partially_filled"}])
    engine._velez_record_initial_risk(pending)
    assert engine._velez_recorded_risk(pending) is None  # its own opening order is still filling


def test_an_incomplete_fill_snapshot_keeps_a_recent_record(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    first = position(0.2)
    first.update(entry_fill={"side": "buy", "transaction_time": recent})
    engine._velez_record_initial_risk(first)
    added = position(0.3)
    added.update(qty="150", entry_price=503.3333333333)  # an add of 50 @ 510 since the last pass
    engine._velez_fills_complete = False  # its fills are missing from a truncated page
    # Can't be told apart from a close and a larger reopen without the fills: not inherited.
    assert engine._velez_open_record(added) is None
    trimmed = position(0.3)
    trimmed.update(qty="60")  # a partial exit: the average entry doesn't move
    assert engine._velez_open_record(trimmed) is not None
    reopened = position(0.3)
    reopened.update(qty="80", entry_price=505.0)  # closed and reopened between passes
    engine._velez_fills_complete = False
    assert engine._velez_open_record(reopened) is None  # neither an add nor an exit of the old trade


def test_opening_decision_never_picks_a_post_fill_add(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    fill = {"transaction_time": "2026-06-03T14:30:00+00:00"}
    opening = {"symbol": "SPY", "side": "buy", "status": "submitted", "timestamp": "2026-06-03T14:29:58+00:00"}
    add = {"symbol": "SPY", "side": "buy", "status": "submitted", "timestamp": "2026-06-03T14:31:00+00:00"}
    monkeypatch.setattr(engine.journal, "decision_entries", lambda limit=80, **kw: [add, opening])
    assert engine._velez_opening_decision("SPY", "long", fill) == opening
    # A market order journaled just after its fill is still found when nothing precedes the fill.
    late = {**opening, "timestamp": "2026-06-03T14:30:01+00:00"}
    monkeypatch.setattr(engine.journal, "decision_entries", lambda limit=80, **kw: [add, late])
    assert engine._velez_opening_decision("SPY", "long", fill) == late


def test_premarket_prints_in_the_opening_hour_are_ignored_when_the_feed_has_the_open():
    strat = strategy(daily_range=True)
    strat.daily_bars_provider = lambda symbol: daily_rows()
    ctx = strat._get_context("SPY")
    # The hourly 09:00 aggregate's 98.0 low printed premarket.
    for b in (hour_bar(9, 100, 100.5, 98.0, 100.2), hour_bar(10, 100.2, 101.2, 100.1, 101.0)):
        ctx.bars.append(Bar(timestamp=b["t"], open=b["o"], high=b["h"], low=b["l"], close=b["c"], volume=1))
    five = lambda minute, low: {"o": 100, "h": 100.4, "l": low, "c": 100.2, "v": 1,
                                "t": datetime(2026, 6, 3, 13, 30, tzinfo=timezone.utc) + timedelta(minutes=minute)}
    strat.session_bars_provider = lambda symbol: [five(0, 99.4), five(5, 99.6)]
    bar = Bar(timestamp=hour_bar(11, 0, 0, 0, 0)["t"], open=101.0, high=101.3, low=100.9, close=101.2, volume=1)
    assert abs(strat._range_used(signal(), bar) - 0.9) < 1e-9  # from the 99.4 session low, not 98.0


def test_planned_limit_entries_are_measured_at_the_limit():
    strat = strategy(daily_range=True)
    strat.daily_bars_provider = lambda symbol: daily_rows()
    strat.session_bars_provider = lambda symbol: [hour_bar(9, 100, 100.5, 99.0, 100.2), hour_bar(10, 100.2, 101.8, 100.1, 101.6)]
    spike = Bar(timestamp=hour_bar(10, 0, 0, 0, 0)["t"], open=100.2, high=101.8, low=100.1, close=101.6, volume=1)
    tail = signal()
    tail.metadata["limit_price"] = 100.8  # a 50% retrace bid
    assert abs(strat._range_used(tail, spike) - 0.9) < 1e-9


def test_daily_bar_closes_early_on_a_half_day(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    monkeypatch.setattr(engine.broker, "is_configured", lambda: True, raising=False)
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("America/New_York")).date()
    calls = []

    def calendar(start=None, end=None):
        calls.append((start, end))
        return [{"date": today.isoformat(), "open": "09:30", "close": "13:00"},
                {"date": "2025-11-28", "open": "09:30", "close": "13:00"}]  # a past half day

    monkeypatch.setattr(engine.broker, "get_calendar_raw", calendar, raising=False)
    bar = Bar(timestamp=datetime(today.year, today.month, today.day, tzinfo=timezone.utc), open=1, high=1, low=1, close=1, volume=1)
    end = engine._velez_bar_end(bar, "1Day", True).astimezone(ZoneInfo("America/New_York"))
    assert (end.hour, end.minute) == (13, 0)
    # A historical half day's bar also ends at 13:00 (after-hours fills that day are after the bar).
    past = Bar(timestamp=datetime(2025, 11, 28, tzinfo=timezone.utc), open=1, high=1, low=1, close=1, volume=1)
    end = engine._velez_bar_end(past, "1Day", True).astimezone(ZoneInfo("America/New_York"))
    assert (end.hour, end.minute) == (13, 0)


def test_opening_decision_is_matched_by_its_order(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    fill = {"transaction_time": "2026-06-03T14:30:00+00:00", "order_id": "ord-7"}
    old_trade = {"symbol": "SPY", "side": "buy", "status": "submitted", "timestamp": "2026-05-20T14:00:00+00:00",
                 "execution_quality": {"order_id": "ord-1"}}
    current = {"symbol": "SPY", "side": "buy", "status": "submitted", "timestamp": "2026-06-03T14:30:01+00:00",
               "execution_quality": {"order_id": "ord-7"}}
    monkeypatch.setattr(engine.journal, "decision_entries", lambda limit=80, **kw: [current, old_trade])
    assert engine._velez_opening_decision("SPY", "long", fill) == current
    # Without order ids, the decision closest to the fill wins over an older trade.
    for d in (current, old_trade):
        d.pop("execution_quality")
    assert engine._velez_opening_decision("SPY", "long", fill) == current


def test_whole_day_minute_counts_are_daily(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    assert engine._velez_alpaca_timeframe("1440") == "1Day"
    assert engine._velez_alpaca_timeframe("120") == "2Hour"


def test_an_ambiguous_linked_decision_is_not_the_entry(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    pos = position(0.5)  # no opening fill, no record (opened before its fills were in view)
    assert engine._velez_entry_time(pos) is not None  # the journal holds no other entry: unambiguous
    decisions = [{"symbol": "SPY", "side": "buy", "status": "submitted", "timestamp": "2026-06-03T14:00:00+00:00"},
                 {"symbol": "SPY", "side": "buy", "status": "submitted", "timestamp": "2026-06-04T14:00:00+00:00"}]
    monkeypatch.setattr(engine.journal, "decision_entries", lambda limit=80, **kw: decisions)
    assert engine._velez_entry_time(pos) is None  # the linked one may be an add
    pos.update(current_price=506.0)
    assert engine._velez_initial_r(pos) is None


def test_cold_start_uses_the_opening_orders_weighted_price(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    at = "2026-06-03T14:30:{:02d}+00:00"
    fills = [{"symbol": "SPY", "side": "buy", "qty": "50", "price": "106", "order_id": "o1", "transaction_time": at.format(2)},
             {"symbol": "SPY", "side": "buy", "qty": "50", "price": "100", "order_id": "o1", "transaction_time": at.format(1)}]
    opening = engine._velez_opening_fill("SPY", True, None, fills, 100)
    assert opening["transaction_time"] == at.format(1) and opening["basis_price"] == 103.0
    decision = {"symbol": "SPY", "side": "buy", "status": "submitted", "stop_price": 95.0, "timestamp": at.format(0)}
    monkeypatch.setattr(engine.journal, "decision_entries", lambda limit=80, **kw: [decision])
    pos = position(None)
    pos.update(entry_fill=opening, entry_price=103.0, stop_price=104.0, current_price=111.0)  # stop trailed
    pos["linked_decision"] = dict(decision)
    engine._velez_record_initial_risk(pos)
    assert engine._velez_recorded_risk(pos) == 8.0  # 103 average to the 95 stop, not 100 to 95


def test_cold_start_after_a_split_finds_the_opening_on_the_new_basis(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    fills = [{"symbol": "SPY", "side": "buy", "qty": "100", "price": "200", "order_id": "o1",
              "transaction_time": "2026-06-03T14:30:00+00:00"}]
    opening = engine._velez_opening_fill("SPY", True, None, fills, 200, 100.0)  # 2-for-1: 200 @ 100
    assert opening is not None and opening["split_factor"] == 2.0
    assert engine._velez_opening_fill("SPY", True, None, fills, 137, 100.0) is None  # not a split ratio
    assert engine._velez_opening_fill("SPY", True, None, fills, 200, 200.0) is None  # cost basis disagrees
    decision = {"symbol": "SPY", "side": "buy", "status": "submitted", "stop_price": 190.0,
                "timestamp": "2026-06-03T14:29:00+00:00"}
    monkeypatch.setattr(engine.journal, "decision_entries", lambda limit=80, **kw: [decision])
    pos = position(None)
    pos.update(entry_fill=opening, qty="200", entry_price=100.0, stop_price=101.0, current_price=106.0)
    pos["linked_decision"] = dict(decision)
    engine._velez_record_initial_risk(pos)
    assert engine._velez_recorded_risk(pos) == 5.0  # (200 - 190) / 2 on today's shares


def test_first_partial_waits_while_a_second_is_pending(monkeypatch, tmp_path):
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    monkeypatch.setattr(engine, "_velez_profit_taking_verdict", lambda p: {"status": "take_partial"})
    engine._record_partial_taken("SPY", "second")  # submitted on an earlier pass, not filled yet
    pending = [{"symbol": "SPY", "client_order_id": "velez-partial-2r-spy-abc", "status": "accepted"}]
    engine._auto_lifecycle_actions(positions=[position(2.4)], open_orders=pending, guardrails=[])
    assert partial_orders(broker) == []  # sized off the old quantity: wait for the 2R order


def test_an_aged_record_is_not_inherited_by_a_reopened_trade(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    first = position(0.2)
    first.update(entry_fill={"side": "buy", "transaction_time": "2026-05-20T14:30:00+00:00"})
    engine._velez_record_initial_risk(first)  # 100 @ 500, opened weeks ago
    held = position(0.3)  # the same trade, its open aged out of the fills
    assert engine._velez_open_record(held) is not None
    reopened = position(0.3)
    reopened.update(qty="70", entry_price=520.0)  # closed and reopened between polls
    assert engine._velez_open_record(reopened) is None


def test_hourly_opening_bar_is_measured_at_its_close():
    strat = strategy(daily_range=True)
    strat.daily_bars_provider = lambda symbol: daily_rows()
    ctx = strat._get_context("SPY")
    prior = hour_bar(8, 100, 100.2, 99.9, 100.0)  # spacing: an hour
    ctx.bars.append(Bar(timestamp=prior["t"], open=100, high=100.2, low=99.9, close=100.0, volume=1))
    five = lambda minute, low: {"o": 100, "h": 100.4, "l": low, "c": 100.2, "v": 1,
                                "t": datetime(2026, 6, 3, 13, 30, tzinfo=timezone.utc) + timedelta(minutes=minute)}
    strat.session_bars_provider = lambda symbol: [five(0, 99.4), five(25, 99.6)]
    # The 09:00 hourly bar (closing 10:00) carries a 98.0 premarket low; the feed's 09:30 bars are in view.
    opening = Bar(timestamp=hour_bar(9, 0, 0, 0, 0)["t"], open=100.0, high=101.4, low=98.0, close=101.2, volume=1)
    assert abs(strat._range_used(signal(), opening) - 0.9) < 1e-9  # from 99.4, not the premarket 98.0


def test_reversal_basis_counts_only_the_new_side(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    at = "2026-06-03T14:30:{:02d}+00:00"
    fills = [{"symbol": "SPY", "side": "buy", "qty": "100", "price": "102", "order_id": "o2", "transaction_time": at.format(3)},
             {"symbol": "SPY", "side": "buy", "qty": "100", "price": "100", "order_id": "o2", "transaction_time": at.format(2)},
             {"symbol": "SPY", "side": "sell", "qty": "100", "price": "99", "order_id": "o1", "transaction_time": at.format(1)}]
    # Short 100, then one 200-share buy order covers at 100 and opens the long at 102.
    opening = engine._velez_opening_fill("SPY", True, None, fills, 100)
    assert opening["transaction_time"] == at.format(3) and opening["basis_price"] == 102.0
    # One fill that both covers and opens: only the 100 past zero is the long's.
    flip = [{"symbol": "SPY", "side": "buy", "qty": "200", "price": "101", "order_id": "o3", "transaction_time": at.format(5)},
            {"symbol": "SPY", "side": "sell", "qty": "100", "price": "99", "order_id": "o1", "transaction_time": at.format(1)}]
    assert engine._velez_opening_fill("SPY", True, None, flip, 100)["basis_price"] == 101.0


def test_opening_decision_prefers_the_one_before_the_fill(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    fill = {"transaction_time": "2026-06-03T14:30:00+00:00"}
    opening = {"symbol": "SPY", "side": "buy", "status": "submitted", "timestamp": "2026-06-03T14:29:30+00:00"}
    add = {"symbol": "SPY", "side": "buy", "status": "submitted", "timestamp": "2026-06-03T14:30:01+00:00"}
    old = {"symbol": "SPY", "side": "buy", "status": "submitted", "timestamp": "2026-05-20T14:00:00+00:00"}
    monkeypatch.setattr(engine.journal, "decision_entries", lambda limit=80, **kw: [add, opening, old])
    assert engine._velez_opening_decision("SPY", "long", fill) == opening  # not the add a second later
    monkeypatch.setattr(engine.journal, "decision_entries", lambda limit=80, **kw: [add, old])
    assert engine._velez_opening_decision("SPY", "long", fill) == add  # journaled just after: not the old trade


def test_opening_timeframe_is_backfilled_when_its_decision_arrives(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    fill = {"side": "buy", "transaction_time": "2026-06-03T14:30:00+00:00"}
    monkeypatch.setattr(engine.journal, "decision_entries", lambda limit=80, **kw: [])
    first = position(0.2)
    first.update(entry_fill=fill)
    first["linked_decision"] = {"timestamp": "2026-06-03T14:30:00+00:00", "stop_price": 495.0}  # no timeframe yet
    engine._velez_record_initial_risk(first)
    assert engine._velez_open_record(first)["timeframe"] is None
    decision = {"symbol": "SPY", "side": "buy", "status": "submitted", "timeframe": "15",
                "timestamp": "2026-06-03T14:30:01+00:00"}
    monkeypatch.setattr(engine.journal, "decision_entries", lambda limit=80, **kw: [decision])
    engine._velez_record_initial_risk(first)
    assert engine._velez_open_record(first)["timeframe"] == "15"


def test_split_evidence_ignores_todays_forming_bar(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("America/New_York")).date()
    rows = [{**r, "split_adjusted": True} for r in daily_rows(70)]
    rows.append({"o": 100, "h": 100, "l": 100, "c": 100.0, "v": 1, "split_adjusted": True,
                 "t": datetime(today.year, today.month, today.day, tzinfo=timezone.utc)})  # cached early today
    monkeypatch.setattr(engine, "_velez_daily_rows", lambda symbol: rows)
    # The stock has since run 15% today: not a split.
    late = {"o": 114, "h": 115.5, "l": 113.8, "c": 115.0, "v": 1,
            "t": datetime.combine(today, datetime.min.time(), tzinfo=ZoneInfo("America/New_York")).replace(hour=15)}
    assert engine._velez_split_in_hold("SPY", [late], False) is False


def test_opening_stop_wins_over_a_wider_current_stop(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    decision = {"symbol": "SPY", "side": "buy", "status": "submitted", "stop_price": 95.0,
                "timestamp": "2026-06-03T14:29:00+00:00"}
    monkeypatch.setattr(engine.journal, "decision_entries", lambda limit=80, **kw: [decision])
    pos = position(None)
    pos.update(entry_fill={"side": "buy", "price": "100", "transaction_time": "2026-06-03T14:30:00+00:00"},
               qty="200", entry_price=110.0, stop_price=100.0, current_price=112.0)  # an add moved the average
    engine._velez_record_initial_risk(pos)
    assert engine._velez_recorded_risk(pos) == 5.0  # the opening's 100 -> 95, not 110 -> 100


def test_fills_showing_a_close_reject_an_add_shaped_reopen(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    first = position(0.2)
    first.update(entry_fill={"side": "buy", "transaction_time": "2026-05-20T14:30:00+00:00"}, entry_price=100.0, stop_price=95.0)
    first["linked_decision"]["stop_price"] = 95.0
    engine._velez_record_initial_risk(first)  # 100 @ 100, aged out of the fills later
    assert engine._velez_recorded_risk(first) == 5.0
    later = datetime.now(timezone.utc) + timedelta(minutes=1)
    reopened = position(0.3)
    reopened.update(qty="150", entry_price=100.0,  # looks like an add of 50 @ 100...
                    velez_symbol_fills=[{"symbol": "SPY", "side": "sell", "qty": "100", "transaction_time": later.isoformat()}])
    assert engine._velez_open_record(reopened) is None  # ...but the fills show the old 100 closed
    added = position(0.3)
    added.update(qty="150", entry_price=100.0, velez_symbol_fills=[])
    engine._velez_fills_complete = True  # a complete snapshot with no close in it: a real add
    assert engine._velez_open_record(added) is not None


def test_first_bar_of_the_session_uses_the_normal_spacing():
    strat = strategy(daily_range=True)
    ctx = strat._get_context("SPY")
    # Yesterday's last 5-minute bars, then today's 09:30 bar after the overnight gap.
    for minute in (45, 50, 55):
        t = datetime(2026, 6, 2, 19, minute, tzinfo=timezone.utc)
        ctx.bars.append(Bar(timestamp=t, open=100, high=100, low=100, close=100, volume=1))
    opening = Bar(timestamp=datetime(2026, 6, 3, 13, 30, tzinfo=timezone.utc), open=100, high=101, low=99, close=100.5, volume=1)
    at = strat._bar_session_time("SPY", opening)
    assert at == opening.timestamp + timedelta(seconds=299)  # 09:34:59 today, not the next day


def test_overnight_hold_measures_the_move_from_within_the_hold(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    # Entered yesterday afternoon off a 95.0 low; today never trades below 99.
    pos = _two_day_hold(monkeypatch, engine, [(96, 97, 95.0, 96.8), (96.8, 98, 96.5, 97.9)],
                        [(99.5, 100.5, 99.2, 100.2), (100.2, 101.5, 100.0, 101.4)], adjusted_yesterday_close=97.9)
    assert engine._velez_profit_taking_verdict(pos)["origin"] == 95.0


def test_extended_hours_bars_do_not_count_as_pushes(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    engine.scanner_config["timeframe"] = "15Min"
    # Entered Wednesday 15:00 ET; three thin after-hours highs, then a quiet Thursday open.
    t = lambda d, h, m: datetime(2026, 6, d, h, m, tzinfo=timezone.utc)
    bars = [Bar(timestamp=t(3, 19, 0), open=100, high=100.5, low=99.8, close=100.2, volume=1),
            Bar(timestamp=t(3, 19, 45), open=100.2, high=100.4, low=100.0, close=100.1, volume=1),
            Bar(timestamp=t(3, 21, 0), open=100.1, high=101.0, low=100.0, close=100.9, volume=1),   # after hours
            Bar(timestamp=t(3, 21, 15), open=100.9, high=100.9, low=100.5, close=100.6, volume=1),
            Bar(timestamp=t(3, 22, 0), open=100.6, high=101.5, low=100.5, close=101.4, volume=1),   # after hours
            Bar(timestamp=t(3, 22, 15), open=101.4, high=101.4, low=101.0, close=101.1, volume=1),
            Bar(timestamp=t(4, 11, 0), open=101.1, high=102.0, low=101.0, close=101.9, volume=1),   # premarket
            Bar(timestamp=t(4, 13, 30), open=101.0, high=101.2, low=100.6, close=100.8, volume=1),
            Bar(timestamp=t(4, 13, 45), open=100.8, high=101.0, low=100.5, close=100.9, volume=1)]
    monkeypatch.setattr(engine, "_fetch_scanner_bars", lambda symbol, asset_type, timeframe=None: bars)
    monkeypatch.setattr(engine, "_velez_daily_rows", lambda symbol: daily_rows(70, last_day=datetime(2026, 6, 3, tzinfo=timezone.utc)))
    monkeypatch.setattr(engine, "_velez_session_bars", lambda symbol, since_day=None: [])
    pos = position(0.5)
    pos["linked_decision"]["timestamp"] = t(3, 19, 1).isoformat()
    assert engine._velez_profit_taking_verdict(pos)["pushes"] < 3


def test_half_day_session_ends_at_the_calendar_close():
    from bot.core.velez_strategy import set_session_close_resolver
    from zoneinfo import ZoneInfo
    ny = ZoneInfo("America/New_York")
    bars = [hour_bar(9, 100, 100.5, 99.0, 100.2), hour_bar(12, 100.2, 101.0, 100.1, 100.9),
            hour_bar(13, 100.9, 103.0, 100.8, 102.8)]  # 13:00 ET: after a half day's close
    set_session_close_resolver(lambda day: datetime.combine(day, datetime.min.time(), tzinfo=ny).replace(hour=13))
    try:
        assert session_high_low_overlap(bars)[0] == 101.0
    finally:
        set_session_close_resolver(None)
    assert session_high_low_overlap(bars)[0] == 103.0


def test_trailed_stop_without_initial_risk_takes_no_r_partial(monkeypatch, tmp_path):
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    monkeypatch.setattr(engine, "_velez_profit_taking_verdict", lambda p: None)
    decisions = [{"symbol": "SPY", "side": "buy", "status": "submitted", "timestamp": "2026-06-03T14:00:00+00:00"},
                 {"symbol": "SPY", "side": "buy", "status": "submitted", "timestamp": "2026-06-04T14:00:00+00:00"}]
    monkeypatch.setattr(engine.journal, "decision_entries", lambda limit=80, **kw: decisions)
    pos = position(60.0)  # current R read off a stop trailed to 500.10
    pos.update(stop_price=500.10, current_price=506.0)
    engine._auto_lifecycle_actions(positions=[pos], open_orders=[], guardrails=[])
    assert partial_orders(broker) == []


def test_split_masked_by_an_exit_is_rebased_from_the_fills(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    at = "2026-06-03T14:{:02d}:00+00:00"
    buy = {"symbol": "SPY", "side": "buy", "qty": "100", "price": "100", "order_id": "o1", "transaction_time": at.format(30)}
    first = position(0.2)
    first.update(entry_fill=engine._velez_opening_fill("SPY", True, None, [buy], 100, 100.0),
                 entry_price=100.0, stop_price=95.0, current_price=101.0)
    first["linked_decision"]["stop_price"] = 95.0
    engine._velez_record_initial_risk(first)  # risk 5
    # Between passes: sell 50, then a 2-for-1 split: still 100 shares, now @ 50.
    sell = {"symbol": "SPY", "side": "sell", "qty": "50", "price": "104", "order_id": "o2", "transaction_time": at.format(45)}
    after = position(None)
    after.update(entry_fill=engine._velez_opening_fill("SPY", True, None, [buy, sell], 100, 50.0),
                 entry_price=50.0, stop_price=50.0, current_price=52.5)
    engine._velez_record_initial_risk(after)
    assert abs(engine._velez_recorded_risk(after) - 2.5) < 1e-9  # halved with the split


def test_no_bounded_opening_decision_means_none(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    old = {"symbol": "SPY", "side": "buy", "status": "submitted", "timestamp": "2026-05-01T14:00:00+00:00"}
    monkeypatch.setattr(engine.journal, "decision_entries", lambda limit=80, **kw: [old])
    assert engine._velez_opening_decision("SPY", "long", {"transaction_time": "2026-06-03T14:30:00+00:00"}) is None


def test_readable_verdict_takes_the_first_partial_without_r(monkeypatch, tmp_path):
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    monkeypatch.setattr(engine, "_velez_profit_taking_verdict", lambda p: {"status": "take_partial"})
    decisions = [{"symbol": "SPY", "side": "buy", "status": "submitted", "timestamp": "2026-06-03T14:00:00+00:00"},
                 {"symbol": "SPY", "side": "buy", "status": "submitted", "timestamp": "2026-06-04T14:00:00+00:00"}]
    monkeypatch.setattr(engine.journal, "decision_entries", lambda limit=80, **kw: decisions)
    pos = position(60.0)  # no initial risk, stop trailed past entry: R is unknown
    pos.update(entry_price=500.0, stop_price=500.10, current_price=506.0)
    engine._auto_lifecycle_actions(positions=[pos], open_orders=[], guardrails=[])
    # The verdict reads profit off entry and price: the first partial comes off, the 2R one doesn't.
    assert [o["client_order_id"].split("-")[2] for o in partial_orders(broker)] == ["1r"]


def test_the_bar_straddling_the_open_is_rebuilt_from_the_session_feed():
    from bot.webhook_server import TradingViewWebhookEngine
    hour = hour_bar(9, 100.0, 105.0, 95.0, 100.8)  # 09:00-10:00 ET with premarket extremes
    pieces = [{"o": 100.2 + 0.1 * i, "h": 100.9, "l": 100.1, "c": 100.5, "v": 1.0,
               "t": datetime(2026, 6, 3, 13, 30, tzinfo=timezone.utc) + timedelta(minutes=5 * i)} for i in range(6)]
    clipped = TradingViewWebhookEngine._velez_rth_clip([hour], pieces, 3600)
    assert [(b["o"], b["h"], b["l"]) for b in clipped] == [(100.2, 100.9, 100.1)]
    # Without the open in the feed the premarket part can't be separated: the bar is left out.
    assert TradingViewWebhookEngine._velez_rth_clip([hour], [], 3600) == []


def test_overnight_origin_ignores_after_hours_prints(monkeypatch, tmp_path):
    import bot.webhook_server as ws
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    yesterday = [(100.0, 100.4, 99.8, 100.2)] * 8 + [(100.2, 100.3, 90.0, 100.1)]  # 16:00 ET: after hours
    pos = _two_day_hold(monkeypatch, engine, yesterday, [(100.4, 101.0, 100.3, 100.9), (100.9, 101.5, 100.8, 101.4)],
                        adjusted_yesterday_close=100.2)
    seen = {}
    original = ws.velez_doctrine.move_origin

    def capture(bars, side):
        seen["low"] = min(b["l"] for b in bars)
        return original(bars, side)

    monkeypatch.setattr(ws.velez_doctrine, "move_origin", capture)
    assert engine._velez_profit_taking_verdict(pos) is not None
    assert seen["low"] >= 99.8


def test_an_add_then_an_exit_of_the_old_size_is_not_a_close(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    record = {"seen_at": "2026-06-03T14:00:00+00:00"}
    add = {"symbol": "SPY", "side": "buy", "qty": "50", "transaction_time": "2026-06-03T14:10:00+00:00"}
    sell = {"symbol": "SPY", "side": "sell", "qty": "100", "transaction_time": "2026-06-03T14:20:00+00:00"}
    pos = {"side": "long", "velez_symbol_fills": [sell, add]}
    assert engine._velez_closed_since(pos, record, 100) is False  # 100 + 50 - 100: still 50 held
    pos["velez_symbol_fills"] = [{**sell, "transaction_time": "2026-06-03T14:05:00+00:00"}, add]
    assert engine._velez_closed_since(pos, record, 100) is True  # flat first, then a new 50


def test_split_evidence_stops_at_a_half_days_close(monkeypatch, tmp_path):
    from zoneinfo import ZoneInfo
    from bot.webhook_server import set_session_close_resolver
    import bot.webhook_server as ws
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    ny = ZoneInfo("America/New_York")
    rows = [{**r, "split_adjusted": True} for r in daily_rows(70, last_day=datetime(2026, 6, 4, tzinfo=timezone.utc))]
    rows[-1]["c"] = 100.0
    monkeypatch.setattr(engine, "_velez_daily_rows", lambda symbol: rows)
    monkeypatch.setattr(ws, "datetime", type("FrozenDatetime", (datetime,), {"now": staticmethod(lambda tz=None: datetime(2026, 6, 5, 16, 0, tzinfo=timezone.utc))}))
    since = [hour_bar(12, 100.0, 100.2, 99.8, 100.0, day=4), hour_bar(14, 100.0, 108.0, 100.0, 107.0, day=4)]
    set_session_close_resolver(lambda day: datetime.combine(day, datetime.min.time(), tzinfo=ny).replace(hour=13))
    try:
        assert engine._velez_split_in_hold("SPY", since, False) is False  # the 14:00 print is after the bell
    finally:
        set_session_close_resolver(None)


def test_a_feed_starting_0935_does_not_cover_the_open():
    from bot.core.velez_strategy import session_feed_covers_open
    piece = lambda minute: {"o": 100, "h": 100.5, "l": 99.5, "c": 100.2, "v": 1.0,
                            "t": datetime(2026, 6, 3, 13, minute, tzinfo=timezone.utc)}
    assert session_feed_covers_open([piece(30), piece(35)], datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc))
    assert not session_feed_covers_open([piece(35), piece(40)], datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc))


def test_push_bars_are_widened_by_the_full_tape_and_prior_opens_need_their_pieces():
    from bot.webhook_server import TradingViewWebhookEngine
    clip = TradingViewWebhookEngine._velez_rth_clip
    ten = hour_bar(10, 100.0, 101.0, 99.9, 100.8)  # IEX
    sip = [{"o": 100.0, "h": 101.6, "l": 99.7, "c": 100.5, "v": 1.0,
            "t": datetime(2026, 6, 3, 14, 20, tzinfo=timezone.utc)}]
    assert [(b["h"], b["l"]) for b in clip([ten], sip, 3600)] == [(101.6, 99.7)]
    # Yesterday's 09:00 bar with only today's pieces: its premarket part can't be separated.
    yesterday_open = hour_bar(9, 100.0, 105.0, 95.0, 100.8, day=2)
    assert clip([yesterday_open, ten], sip, 3600) == []


def test_a_later_add_is_not_the_opening_decision_of_a_fill_without_one(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    first = {"symbol": "SPY", "side": "buy", "status": "submitted", "stop_price": 480.0, "timestamp": "2026-05-01T14:00:00+00:00"}
    add = {"symbol": "SPY", "side": "buy", "status": "submitted", "stop_price": 480.0, "timestamp": "2026-05-02T14:00:00+00:00"}
    monkeypatch.setattr(engine.journal, "decision_entries", lambda limit=80, **kw: [add, first])
    pos = position(None)
    pos.update(entry_fill={"side": "buy", "price": "500", "transaction_time": "2026-06-03T14:30:00+00:00"},
               entry_price=500.0, stop_price=495.0, current_price=503.0)
    pos["linked_decision"] = dict(add)
    engine._velez_record_initial_risk(pos)
    assert engine._velez_recorded_risk(pos) == 5.0  # the live stop, not the add's 480


def test_a_fractional_long_stock_position_takes_a_fractional_partial(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    pos = position(1.2)
    pos["qty"] = "1.5"
    assert engine._velez_partial_qty(pos, 0.5) == 0.75
    pos["qty"] = "101"
    assert engine._velez_partial_qty(pos, 0.5) == 50.0  # whole shares stay whole (maybe not fractionable)


def test_the_stop_is_resized_around_a_partial(monkeypatch, tmp_path):
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    monkeypatch.setattr(engine, "_velez_profit_taking_verdict", lambda p: {"status": "take_partial"})
    broker.orders = [{"id": "s1", "symbol": "SPY", "type": "stop", "side": "sell", "qty": "100", "stop_price": "497", "status": "new"}]
    engine._auto_lifecycle_actions(positions=[position(0.6)], open_orders=[], guardrails=[])
    assert broker.canceled == ["s1"]
    stops = [o for o in broker.submitted if str(o.get("client_order_id", "")).startswith("velez-runner-stop-")]
    assert [(o["qty"], o["stop_price"]) for o in stops] == [("50", "497.00")]
    assert broker.submitted.index(partial_orders(broker)[0]) < broker.submitted.index(stops[0])


def test_a_failed_partial_puts_the_whole_stop_back(monkeypatch, tmp_path):
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    broker.orders = [{"id": "s1", "symbol": "SPY", "type": "stop", "side": "sell", "qty": "100", "stop_price": "497", "status": "new"}]

    def refuse():
        raise RuntimeError("rejected")

    import pytest
    with pytest.raises(RuntimeError):
        engine._velez_partial_with_stop(position(0.6), 50, refuse)
    stops = [o for o in broker.submitted if str(o.get("client_order_id", "")).startswith("velez-runner-stop-")]
    assert [(o["qty"], o["stop_price"]) for o in stops] == [("100", "497.00")]


def test_a_split_read_off_fills_with_a_post_split_add_is_not_trusted(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    at = "2026-06-03T14:{:02d}:00+00:00"
    buy = {"symbol": "SPY", "side": "buy", "qty": "100", "price": "100", "order_id": "o1", "transaction_time": at.format(30)}
    add = {"symbol": "SPY", "side": "buy", "qty": "100", "price": "60", "order_id": "o2", "transaction_time": at.format(50)}
    # 2-for-1 between the fills: 300 held at 53.33 reads as a 3-for-2 split off the fills.
    assert engine._velez_opening_fill("SPY", True, None, [buy, add], 300, 160 / 3) is None
    # Without the add the 2-for-1 is read.
    assert engine._velez_opening_fill("SPY", True, None, [buy], 200, 50.0)["split_factor"] == 2.0


def test_an_old_lone_decision_is_not_a_manual_positions_opening(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    old = {"symbol": "SPY", "side": "buy", "status": "submitted", "stop_price": 480.0, "timestamp": "2026-03-01T14:00:00+00:00"}
    monkeypatch.setattr(engine.journal, "decision_entries", lambda limit=80, **kw: [old])
    pos = position(None)
    pos.update(entry_fill={"side": "buy", "price": "500", "transaction_time": "2026-06-03T14:30:00+00:00"},
               entry_price=500.0, stop_price=495.0, current_price=503.0)
    pos["linked_decision"] = dict(old)  # the symbol's only decision, months before this manual entry
    engine._velez_record_initial_risk(pos)
    assert engine._velez_recorded_risk(pos) == 5.0  # the live stop, not the old trade's 480


def _stop(order_id, side, price, qty="100"):
    return {"id": order_id, "symbol": "SPY", "type": "stop", "side": side, "qty": qty, "stop_price": price, "status": "new"}


def _runner_stops(broker):
    return [o for o in broker.submitted if str(o.get("client_order_id", "")).startswith("velez-runner-stop-")]


def test_a_buy_stop_entry_is_not_taken_for_the_long_positions_protection(monkeypatch, tmp_path):
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    broker.orders = [_stop("s1", "sell", "495"), _stop("add", "buy", "505", qty="20")]
    engine._velez_partial_with_stop(position(0.6), 50, lambda: broker.submit_order_payload({"client_order_id": "velez-partial-1r-x"}))
    assert broker.canceled == ["s1"]
    assert [(o["qty"], o["stop_price"]) for o in _runner_stops(broker)] == [("50", "495.00")]


def test_a_failed_stop_cancel_holds_the_partial(monkeypatch, tmp_path):
    import pytest
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    broker.orders = [_stop("s1", "sell", "495", qty="60"), _stop("s2", "sell", "496", qty="40")]
    original = broker.cancel_order

    def cancel(order_id):
        if order_id == "s2":
            raise RuntimeError("broker timeout")
        return original(order_id)

    monkeypatch.setattr(broker, "cancel_order", cancel)
    sent = []
    pos = position(0.6)
    with pytest.raises(RuntimeError):
        engine._velez_partial_with_stop(pos, 50, lambda: sent.append(1))
    assert sent == []  # the exit never went out
    # The follow-up tops the stops back up: s2 still covers 40, so 60 more at the cancelled price.
    assert engine._velez_reconcile_partial_stop(pos)["status"] == "submitted"
    assert [(o["qty"], o["stop_price"]) for o in _runner_stops(broker)] == [("60", "496.00")]


def test_a_runner_left_without_its_stop_is_a_failed_action(monkeypatch, tmp_path):
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    monkeypatch.setattr(engine, "_velez_profit_taking_verdict", lambda p: {"status": "take_partial"})
    broker.orders = [_stop("s1", "sell", "497")]
    monkeypatch.setattr(engine, "_velez_place_stop", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("rejected")))
    alerts = []
    monkeypatch.setattr(engine, "_notify_event", lambda **kw: alerts.append(kw))
    actions = engine._auto_lifecycle_actions(positions=[position(0.6)], open_orders=[], guardrails=[])
    partial = [a for a in actions if a["action"] == "partial_first_r"]
    assert partial and partial[0]["status"] == "failed" and "runner stop" in partial[0]["error"]
    assert alerts and alerts[0]["severity"] == "critical"
    # The exit itself went out (and filled) and is recorded: the next pass doesn't sell again.
    filled = position(0.6)
    filled["qty"] = "50"
    engine._auto_lifecycle_actions(positions=[filled], open_orders=[], guardrails=[])
    assert len(partial_orders(broker)) == 1


def test_the_second_partial_waits_for_the_verdicts_first(monkeypatch, tmp_path):
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    monkeypatch.setattr(engine, "_velez_profit_taking_verdict", lambda p: {"status": "hold"})
    engine._auto_lifecycle_actions(positions=[position(2.4)], open_orders=[], guardrails=[])
    assert partial_orders(broker) == []  # past 2R, but the rulebook hasn't called the first partial yet


def test_the_open_record_is_kept_without_an_initial_risk(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    pos = position(None)  # a manual trade first seen with its stop already at breakeven
    pos.update(entry_fill={"side": "buy", "transaction_time": "2026-06-03T14:30:00+00:00"},
               entry_price=500.0, stop_price=500.0, current_price=506.0)
    pos["linked_decision"] = {}
    engine._velez_record_initial_risk(pos)
    record = engine._velez_open_record(pos)
    assert record is not None and record["risk"] is None and record["opened"] == "2026-06-03T14:30:00+00:00"
    assert engine._velez_recorded_risk(pos) is None


def test_a_stop_without_a_readable_price_is_never_cancelled(monkeypatch, tmp_path):
    import pytest
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    trailing = {"id": "t1", "symbol": "SPY", "type": "trailing_stop", "side": "sell", "qty": "100", "trail_percent": "2", "status": "new"}
    broker.orders = [trailing]
    sent = []
    with pytest.raises(RuntimeError):
        engine._velez_partial_with_stop(position(0.6), 50, lambda: sent.append(1))
    assert broker.canceled == [] and sent == []


def test_a_sub_cent_stop_is_never_cancelled(monkeypatch, tmp_path):
    import pytest
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    broker.orders = [_stop("s1", "sell", "0.000009")]
    with pytest.raises(RuntimeError):
        engine._velez_partial_with_stop(position(0.6), 50, lambda: None)
    assert broker.canceled == []


def test_equity_partials_wait_for_the_regular_session(monkeypatch, tmp_path):
    import bot.webhook_server as ws
    from bot.webhook_server import TradingViewWebhookEngine
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    window = lambda now: TradingViewWebhookEngine._velez_partial_window_open(engine, "SPY") if not monkeypatch.setattr(
        ws, "datetime", type("FrozenDatetime", (datetime,), {"now": staticmethod(lambda tz=None: now if tz is None else now.astimezone(tz))})) else None
    monkeypatch.setattr(engine, "_velez_session_close", lambda day, default: default)
    assert window(datetime(2026, 6, 3, 15, 0, tzinfo=timezone.utc)) is False   # the calendar didn't confirm today
    engine._velez_open_days = {datetime(2026, 6, 3).date(), datetime(2026, 6, 6).date()}
    assert window(datetime(2026, 6, 3, 15, 0, tzinfo=timezone.utc)) is True    # Wed 11:00 ET
    assert window(datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)) is False   # 08:00 ET premarket
    assert window(datetime(2026, 6, 3, 19, 58, tzinfo=timezone.utc)) is False  # 15:58 ET: too close to the bell
    assert window(datetime(2026, 6, 6, 15, 0, tzinfo=timezone.utc)) is False   # Saturday


def test_an_exit_that_never_fills_gets_its_full_stop_back(monkeypatch, tmp_path):
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    broker.orders = [_stop("s1", "sell", "497")]
    pos = position(0.6)
    engine._velez_partial_with_stop(pos, 50, lambda: {"id": "x1", "client_order_id": "velez-partial-1r-x"})
    assert [o["qty"] for o in _runner_stops(broker)] == ["50"]
    runner = dict(_runner_stops(broker)[0], id="r1", status="new", stop_price="497")
    # Still working: wait.
    broker.orders = [runner, {"id": "x1", "symbol": "SPY", "type": "market", "side": "sell", "status": "new"}]
    assert engine._velez_reconcile_partial_stop(pos) is None
    # Rejected: the position is still 100, the runner stop covers 50 - topped up by 50 at the same price.
    broker.orders = [runner]
    result = engine._velez_reconcile_partial_stop(pos)
    assert result["status"] == "submitted" and result["qty"] == 50
    assert [(o["qty"], o["stop_price"]) for o in _runner_stops(broker)] == [("50", "497.00"), ("50", "497.00")]
    assert engine._velez_reconcile_partial_stop(pos) is None  # done


def test_a_filled_exit_clears_the_follow_up(monkeypatch, tmp_path):
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    broker.orders = [_stop("s1", "sell", "497")]
    engine._velez_partial_with_stop(position(0.6), 50, lambda: {"id": "x1"})
    broker.orders = [dict(_runner_stops(broker)[0], id="r1", status="new")]  # the runner covers the 50 left
    after = position(0.6)
    after["qty"] = "50"
    assert engine._velez_reconcile_partial_stop(after) is None
    assert not engine.journal.get_setting("velez_partial_resize.SPY", None)


def test_a_failed_calendar_read_is_not_retried_for_every_bar(monkeypatch, tmp_path):
    from zoneinfo import ZoneInfo
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    calls = []

    def calendar(**kw):
        calls.append(kw)
        raise RuntimeError("calendar down")

    broker.get_calendar_raw = calendar
    day = datetime(2026, 6, 3).date()
    default = datetime(2026, 6, 3, 16, 0, tzinfo=ZoneInfo("America/New_York"))
    for _ in range(50):
        assert engine._velez_session_close(day, default) == default
    assert len(calls) == 1


def test_a_stop_still_pending_cancellation_holds_the_exit(monkeypatch, tmp_path):
    import pytest
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    monkeypatch.setattr(broker, "cancel_order", lambda order_id: broker.canceled.append(order_id) or {})  # acknowledged only
    broker.orders = [_stop("s1", "sell", "497")]
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    sent = []
    with pytest.raises(RuntimeError):
        engine._velez_partial_with_stop(position(0.6), 50, lambda: sent.append(1))
    assert sent == []  # still holding the shares: no exit


def test_a_partly_filled_exit_gets_the_rest_covered(monkeypatch, tmp_path):
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    broker.orders = [_stop("s1", "sell", "497")]
    engine._velez_partial_with_stop(position(0.6), 50, lambda: {"id": "x1"})
    broker.orders = [dict(_runner_stops(broker)[0], id="r1", status="new")]  # runner: 50; exit ended after 20
    after = position(0.6)
    after["qty"] = "80"
    assert engine._velez_reconcile_partial_stop(after)["qty"] == 30


def test_a_bar_past_the_close_is_rebuilt_from_session_pieces():
    from bot.webhook_server import TradingViewWebhookEngine
    clip = TradingViewWebhookEngine._velez_rth_clip
    four = {"o": 100.0, "h": 104.0, "l": 96.0, "c": 103.0, "v": 1.0, "t": datetime(2026, 6, 3, 17, 0, tzinfo=timezone.utc)}  # 13:00-17:00 ET
    pieces = [{"o": 100.0 + i * 0.01, "h": 101.0, "l": 99.5, "c": 100.5, "v": 1.0,
               "t": datetime(2026, 6, 3, 17, 0, tzinfo=timezone.utc) + timedelta(minutes=5 * i)} for i in range(36)]  # 13:00-16:00
    rebuilt = clip([four], pieces, 4 * 3600)
    assert [(b["h"], b["l"], b["c"]) for b in rebuilt] == [(101.0, 99.5, 100.5)]  # no after-hours 104 / 96
    assert clip([four], pieces[:30], 4 * 3600) == []  # the last half hour missing: can't be separated


def test_futures_and_forex_partials_respect_their_closures(monkeypatch, tmp_path):
    import bot.webhook_server as ws
    from bot.webhook_server import TradingViewWebhookEngine
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")

    def window(asset, now):
        monkeypatch.setattr(engine, "_quote_asset_type", lambda symbol: asset)
        monkeypatch.setattr(ws, "datetime", type("FrozenDatetime", (datetime,), {"now": staticmethod(lambda tz=None: now if tz is None else now.astimezone(tz))}))
        return TradingViewWebhookEngine._velez_partial_window_open(engine, "X")

    assert window("futures", datetime(2026, 6, 3, 15, 0, tzinfo=timezone.utc)) is True    # Wed 11:00 ET
    assert window("futures", datetime(2026, 6, 3, 21, 30, tzinfo=timezone.utc)) is False  # 17:30 ET daily halt
    assert window("futures", datetime(2026, 6, 6, 15, 0, tzinfo=timezone.utc)) is False   # Saturday
    assert window("forex", datetime(2026, 6, 5, 22, 0, tzinfo=timezone.utc)) is False     # Friday 18:00 ET
    assert window("forex", datetime(2026, 6, 3, 21, 30, tzinfo=timezone.utc)) is True
    assert window("crypto", datetime(2026, 6, 6, 15, 0, tzinfo=timezone.utc)) is True


def test_an_unfilled_first_partial_can_fire_again(monkeypatch, tmp_path):
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    broker.orders = [_stop("s1", "sell", "497")]
    engine._velez_partial_with_stop(position(0.6), 50, level="first", submit=lambda: {"id": "x1"})
    engine._record_partial_taken("SPY", "first")
    broker.orders = [dict(_runner_stops(broker)[0], id="r1", status="new")]  # the exit was rejected
    engine._velez_reconcile_partial_stop(position(0.6))
    assert "first" not in engine._partials_taken_for_symbol("SPY")


def test_an_oversized_stop_after_the_exit_is_cut_to_the_runner(monkeypatch, tmp_path):
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    broker.orders = [_stop("s1", "sell", "497")]
    engine._velez_partial_with_stop(position(0.6), 50, lambda: {"id": "x1"})
    broker.orders = [_stop("big", "sell", "500")]  # a stop moved back to full size while the exit worked
    after = position(0.6)
    after["qty"] = "50"
    result = engine._velez_reconcile_partial_stop(after)
    assert result["status"] == "submitted" and "big" in broker.canceled
    assert [(o["qty"], o["stop_price"]) for o in _runner_stops(broker)][-1] == ("50", "500.00")


def test_a_flat_symbol_drops_its_stop_follow_up(monkeypatch, tmp_path):
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    broker.orders = [_stop("s1", "sell", "497")]
    engine._velez_partial_with_stop(position(0.6), 50, lambda: {"id": "x1"})
    engine._velez_prune_open_records(set())  # SPY is flat
    assert not engine.journal.get_setting("velez_partial_resize.SPY", None)


def test_stop_moves_wait_while_a_partial_is_working(monkeypatch, tmp_path):
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    broker.orders = [_stop("s1", "sell", "497")]
    engine._velez_partial_with_stop(position(0.6), 50, lambda: {"id": "x1"})
    broker.orders = [{"id": "x1", "symbol": "SPY", "type": "market", "side": "sell", "status": "new"}]
    before = len(broker.submitted)
    engine._auto_lifecycle_actions(positions=[position(1.5)], open_orders=[], guardrails=[])  # breakeven would fire
    assert not [o for o in broker.submitted[before:] if o.get("type") == "stop"]


def test_a_timed_out_exit_the_broker_has_is_not_sold_again(monkeypatch, tmp_path):
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    broker.orders = [_stop("s1", "sell", "497")]

    def timeout():
        broker.orders = [{"id": "x1", "client_order_id": "velez-partial-1r-abc", "symbol": "SPY", "type": "market", "side": "sell", "status": "new"}]
        raise TimeoutError("read timed out")

    error = engine._velez_partial_with_stop(position(0.6), 50, timeout, level="first", client_order_id="velez-partial-1r-abc")
    assert "unconfirmed" in error
    assert "first" in engine._partials_taken_for_symbol("SPY")  # treated as sent: not sold twice
    assert [o["qty"] for o in _runner_stops(broker)] == ["50"]
    assert engine.journal.get_setting("velez_partial_resize.SPY", None)["client_order_id"] == "velez-partial-1r-abc"


def test_a_refused_exit_unmarks_its_level_and_restores_the_stop(monkeypatch, tmp_path):
    import pytest
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    broker.orders = [_stop("s1", "sell", "497")]

    def refuse():
        raise RuntimeError("insufficient qty")

    with pytest.raises(RuntimeError):
        engine._velez_partial_with_stop(position(0.6), 50, refuse, level="first", client_order_id="velez-partial-1r-def")
    assert "first" not in engine._partials_taken_for_symbol("SPY")
    assert [o["qty"] for o in _runner_stops(broker)] == ["100"]
    assert not engine.journal.get_setting("velez_partial_resize.SPY", None)


def test_a_timed_out_stop_the_broker_has_is_not_sent_twice(monkeypatch, tmp_path):
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    broker.orders = [_stop("s1", "sell", "497")]
    sent = []

    def place(symbol, side, qty, stop_price, client_order_id=None):
        sent.append(client_order_id)
        broker.orders = [{"id": "r1", "client_order_id": client_order_id, "symbol": "SPY", "type": "stop", "side": "sell", "qty": "50", "status": "new"}]
        raise TimeoutError("read timed out")

    monkeypatch.setattr(engine, "_velez_place_stop", place)
    assert engine._velez_partial_with_stop(position(0.6), 50, lambda: {"id": "x1"}) is None
    assert len(sent) == 1


def test_no_new_partial_while_a_previous_one_is_followed_up(monkeypatch, tmp_path):
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    monkeypatch.setattr(engine, "_velez_profit_taking_verdict", lambda p: {"status": "take_partial"})
    engine.journal.set_setting("velez_partial_resize.SPY", {"full_qty": 100, "exit_qty": 50, "stop_price": 497.0, "order_id": "x1"})
    broker.orders = [{"id": "x1", "symbol": "SPY", "type": "market", "side": "sell", "status": "new"}]
    engine._auto_lifecycle_actions(positions=[position(0.6)], open_orders=[], guardrails=[])
    assert partial_orders(broker) == []


def test_a_one_for_twenty_five_reverse_split_is_read():
    from bot.webhook_server import TradingViewWebhookEngine
    assert TradingViewWebhookEngine._velez_split_ratio(1 / 25) == (1, 25)
    assert TradingViewWebhookEngine._velez_split_ratio(1 / 50) == (1, 50)
    assert TradingViewWebhookEngine._velez_split_ratio(0.0371) is None


def test_a_sell_short_add_is_not_a_close(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    record = {"seen_at": "2026-06-03T14:00:00+00:00"}
    add = {"symbol": "SPY", "side": "sell_short", "qty": "50", "transaction_time": "2026-06-03T14:10:00+00:00"}
    cover = {"symbol": "SPY", "side": "buy", "qty": "100", "transaction_time": "2026-06-03T14:20:00+00:00"}
    assert engine._velez_closed_since({"side": "short", "velez_symbol_fills": [add, cover]}, record, 100) is False


def test_a_bar_history_reads_the_calendar_once(monkeypatch, tmp_path):
    engine, broker = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    calls = []
    broker.get_calendar_raw = lambda start=None, end=None: calls.append((start, end)) or [
        {"date": "2026-05-%02d" % d, "close": "16:00"} for d in range(1, 29)]
    for d in range(4, 28):
        engine._velez_bar_end(Bar(timestamp=datetime(2026, 5, d, tzinfo=timezone.utc), open=1, high=1, low=1, close=1, volume=1), "1Day", True)
    assert len(calls) == 1


def test_index_futures_roll_to_the_front_month():
    from datetime import date
    from bot.webhook_server import front_month_index_contract
    assert front_month_index_contract(date(2026, 10, 2)) == "Z6"
    assert front_month_index_contract(date(2026, 12, 9)) == "Z6"    # Dec 2026 expires Fri 18th: roll on the 10th
    assert front_month_index_contract(date(2026, 12, 10)) == "H7"
    assert front_month_index_contract(date(2027, 3, 10)) == "H7"    # Mar 2027 expires Fri 19th: roll on the 11th
    assert front_month_index_contract(date(2027, 3, 11)) == "M7"
    assert front_month_index_contract(date(2026, 6, 1)) == "M6"


def test_configured_futures_contracts_still_win(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    assert engine._polygon_futures_ticker("ES").startswith("ES") and engine._polygon_futures_ticker("ES") != "ESM6"
    engine.scanner_config["futures_contracts"] = {"ES": "ESU6"}
    assert engine._polygon_futures_ticker("ES") == "ESU6"
    assert engine._polygon_futures_ticker("GC") == "GC"


def test_an_add_shape_needs_fills_that_reach_back_to_the_last_sighting(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    first = position(0.2)
    first.update(entry_fill={"side": "buy", "transaction_time": "2026-05-20T14:30:00+00:00"}, entry_price=100.0, stop_price=95.0)
    engine._velez_record_initial_risk(first)
    record = engine.journal.get_setting("velez_initial_risk.SPY.open", None)
    record["seen_at"] = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()  # last seen before an outage
    engine.journal.set_setting("velez_initial_risk.SPY.open", record)
    added = position(0.3)
    added.update(qty="150", entry_price=100.0, velez_symbol_fills=[])
    engine._velez_fills_complete = True
    assert engine._velez_open_record(added) is None  # the fill window can't show what happened 30 days ago


def test_an_unexecuted_linked_decision_is_not_the_opening(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    monkeypatch.setattr(engine.journal, "decision_entries", lambda limit=80, **kw: [])
    pos = position(0.5)
    pos["linked_decision"] = {"symbol": "SPY", "side": "buy", "status": "diagnostic", "timestamp": "2026-06-03T14:00:00+00:00", "stop_price": 495.0}
    assert engine._velez_linked_is_only_entry(pos) is False
    for status in ("submitted", "proposed"):  # an approved trade stays "proposed"
        pos["linked_decision"]["status"] = status
        assert engine._velez_linked_is_only_entry(pos) is True


def test_the_fill_window_starts_at_midnight_like_the_broker_request(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    first = position(0.2)
    first.update(entry_fill={"side": "buy", "transaction_time": "2026-05-20T14:30:00+00:00"}, entry_price=100.0, stop_price=95.0)
    engine._velez_record_initial_risk(first)
    record = engine.journal.get_setting("velez_initial_risk.SPY.open", None)
    now = datetime.now(timezone.utc)
    boundary = datetime.combine((now - timedelta(days=7)).date(), datetime.min.time(), tzinfo=timezone.utc)
    record["seen_at"] = (boundary + timedelta(minutes=1)).isoformat()  # over 7 days ago, but inside the fetched window
    engine.journal.set_setting("velez_initial_risk.SPY.open", record)
    added = position(0.3)
    added.update(qty="150", entry_price=100.0, velez_symbol_fills=[])
    engine._velez_fills_complete = True
    assert engine._velez_open_record(added) is not None


def test_a_contract_roll_restarts_the_scanner_history(monkeypatch, tmp_path):
    engine, _ = lifecycle_engine(monkeypatch, tmp_path, "velez_profit_taking")
    engine.scanner_config["futures_contracts"] = {"ES": "ESZ6"}
    engine._scanner_reset_on_contract_roll("ES")
    engine.scanner_last_bar["ES"] = datetime.now(timezone.utc)
    engine.scanner_strategy.symbols["ES"] = object()
    engine._scanner_reset_on_contract_roll("ES")  # same contract: kept
    assert "ES" in engine.scanner_last_bar and "ES" in engine.scanner_strategy.symbols
    engine.scanner_config["futures_contracts"] = {"ES": "ESH7"}
    engine._scanner_reset_on_contract_roll("ES")
    assert "ES" not in engine.scanner_last_bar and "ES" not in engine.scanner_strategy.symbols
