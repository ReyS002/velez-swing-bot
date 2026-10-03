from bot.webhook_server import TradingViewWebhookEngine


def _config(**webhook):
    return {
        "portfolio": {"initial_cash": 100000},
        "risk": {"risk_per_trade": 0.005, "max_dollar_risk_per_trade": 1000, "max_daily_loss_pct": 0.02,
                 "max_consecutive_losses": 3, "max_open_positions": 3, "max_leverage": 2.0,
                 "max_order_qty": 10000, "max_stop_pct": 0.1},
        "webhook": {"auth_required": True, "secret": "test-secret", "execute_orders": False, "paper_only": True,
                    "time_in_force": "day", **webhook},
        "event_filter": {"enabled": False},
        "symbols": [{"symbol": "SPY", "contract_multiplier": 1}, {"symbol": "BTCUSD", "type": "crypto", "contract_multiplier": 1}],
        "velez_strategy": {},
    }


def _signal(timestamp, symbol="SPY"):
    return {"mode": "signal", "symbol": symbol, "side": "sell", "play": "elephant_bar", "order_type": "market",
            "entry_price": 500, "stop_price": 502, "timestamp": timestamp}


def _engine(**webhook):
    from datetime import date
    engine = TradingViewWebhookEngine(_config(**webhook))
    # The exchange calendar confirms these as trading days (the test engine has no broker to ask).
    engine.__dict__["_velez_open_days"] = {date(2026, 10, 1), date(2026, 10, 2), date(2026, 11, 27)}
    engine.__dict__["_velez_closed_days"] = {date(2026, 11, 26)}
    return engine


def _decision(engine, timestamp, symbol="SPY", clock=None):
    from datetime import datetime
    stamp = clock or timestamp
    engine._regular_hours_clock = lambda: datetime.fromisoformat(stamp.replace("Z", "+00:00"))  # delivered on time
    return engine.handle_payload(_signal(timestamp, symbol), path_token="test-secret")["decisions"][0]


def test_an_equity_alert_after_the_bell_is_rejected():
    engine = _engine(regular_hours_only=True)
    decision = _decision(engine, "2026-10-01T20:00:44Z")  # Thu 16:00:44 ET: the HOOD / TSLA case
    assert decision["status"] == "rejected" and decision["reason"].startswith("outside_regular_hours:")


def test_premarket_and_weekend_alerts_are_rejected_too():
    engine = _engine(regular_hours_only=True)
    assert _decision(engine, "2026-10-02T13:00:00Z")["status"] == "rejected"   # Fri 09:00 ET
    assert _decision(engine, "2026-10-03T15:00:00Z")["status"] == "rejected"   # Saturday


def test_alerts_inside_the_session_still_go_through():
    engine = _engine(regular_hours_only=True)
    assert _decision(engine, "2026-10-01T15:30:00Z")["status"] != "rejected"    # Thu 11:30 ET
    assert _decision(engine, "2026-10-01T19:55:00Z")["status"] != "rejected"    # Thu 15:55 ET


def test_non_equity_symbols_are_not_limited_to_the_session():
    engine = _engine(regular_hours_only=True)
    assert not _decision(engine, "2026-10-03T15:00:00Z", "BTCUSD")["reason"].startswith("outside_regular_hours")


def test_the_gate_is_opt_in():
    engine = _engine()
    assert not str(_decision(engine, "2026-10-01T20:00:44Z")["reason"]).startswith("outside_regular_hours")


def test_a_half_day_closes_at_the_calendar_time():
    from datetime import date, datetime
    from zoneinfo import ZoneInfo
    engine = _engine(regular_hours_only=True)
    day = date(2026, 11, 27)  # the Friday after Thanksgiving
    engine.__dict__.setdefault("_velez_close_cache", {})[day] = datetime(2026, 11, 27, 13, 0, tzinfo=ZoneInfo("America/New_York"))
    assert _decision(engine, "2026-11-27T17:30:00Z")["status"] != "rejected"    # 12:30 ET, still open
    late = _decision(engine, "2026-11-27T18:30:00Z")                            # 13:30 ET, after the early close
    assert late["status"] == "rejected" and late["reason"].startswith("outside_regular_hours:")


def test_a_market_holiday_is_rejected():
    from datetime import date
    engine = _engine(regular_hours_only=True)
    engine.__dict__.setdefault("_velez_closed_days", set()).add(date(2026, 11, 26))  # Thanksgiving
    assert _decision(engine, "2026-11-26T15:00:00Z")["status"] == "rejected"


def test_the_time_alias_is_honored():
    engine = _engine(regular_hours_only=True)
    payload = _signal("2026-10-01T15:30:00Z")
    payload["time"] = "2026-10-01T20:00:44Z"  # after the bell
    del payload["timestamp"]
    decision = engine.handle_payload(payload, path_token="test-secret")["decisions"][0]
    assert decision["status"] == "rejected" and decision["reason"].startswith("outside_regular_hours:")


def test_the_gate_covers_every_order_built_not_just_signals():
    from bot.core.types import Side, Signal
    engine = _engine(regular_hours_only=True)
    signal = Signal("SPY", Side.SELL, "bear_180", {"entry_price": 500, "stop_price": 502, "order_type": "limit",
                                                   "timestamp": "2026-10-01T20:00:44Z"})
    decision = engine._build_order_decision(signal, "alert-1")
    assert decision.status == "rejected" and decision.reason.startswith("outside_regular_hours:")


def test_an_approval_after_the_bell_is_cancelled(monkeypatch):
    engine = _engine(regular_hours_only=True)
    cancelled = []
    monkeypatch.setattr(engine, "_authorize_approval_token", lambda token: {"ok": True})
    monkeypatch.setattr(engine, "_execute_orders", lambda: True)
    monkeypatch.setattr(engine, "_paper_broker_endpoint", lambda: True)
    monkeypatch.setattr(engine.journal, "get_pending_order", lambda approval_id: {"symbol": "SPY", "order_payload": {}})
    monkeypatch.setattr(engine, "_session_lock_entry_state", lambda *args, **kwargs: {"entry_allowed": True})
    monkeypatch.setattr(engine, "_regular_hours_block", lambda symbol, timestamp=None: {"clock": "Thu 16:05:00 ET", "allowed": "x"})
    monkeypatch.setattr(engine.journal, "cancel_staged_pending_order", lambda approval_id, reason: cancelled.append(reason) or None)
    monkeypatch.setattr(engine.journal, "_public_pending", lambda pending: pending)
    result = engine.approve_pending_order("abc", "phrase", "token")
    assert result["ok"] is False and result["reason"].startswith("outside_regular_hours:") and cancelled


def test_a_delivery_after_the_bell_is_rejected_even_if_the_alert_was_in_session():
    engine = _engine(regular_hours_only=True)
    decision = _decision(engine, "2026-10-01T19:55:00Z", clock="2026-10-01T20:03:00Z")  # alert 15:55, delivered 16:03
    assert decision["status"] == "rejected" and decision["reason"].startswith("outside_regular_hours:")


def test_equity_aliases_are_gated_and_a_missing_calendar_fails_closed():
    from datetime import datetime
    config = _config(regular_hours_only=True)
    config["symbols"] = [{"symbol": "SPY", "type": "stocks", "contract_multiplier": 1}]
    engine = TradingViewWebhookEngine(config)  # no calendar confirmation at all
    engine._regular_hours_clock = lambda: datetime.fromisoformat("2026-10-01T15:30:00+00:00")
    decision = engine.handle_payload(_signal("2026-10-01T15:30:00Z"), path_token="test-secret")["decisions"][0]
    assert decision["status"] == "rejected" and "calendar" in decision["metadata"]["regular_hours"]["allowed"]
    from datetime import date
    engine.__dict__["_velez_open_days"] = {date(2026, 10, 1)}  # once the calendar confirms the day, an alias is admitted
    assert engine.handle_payload(_signal("2026-10-01T15:31:00Z"), path_token="test-secret")["decisions"][0]["status"] != "rejected"


def test_a_dry_run_is_not_limited_to_the_session():
    from bot.core.types import Side, Signal
    engine = _engine(regular_hours_only=True)
    signal = Signal("SPY", Side.SELL, "bear_180", {"entry_price": 500, "stop_price": 502, "order_type": "limit",
                                                   "timestamp": "2026-10-01T20:00:44Z"})
    live = engine._build_order_decision(signal, "alert-1")
    dry = engine._build_order_decision(signal, "alert-2", dry_run=True)
    assert live.status == "rejected" and dry.reason != live.reason and not str(dry.reason).startswith("outside_regular_hours")


def test_an_unreadable_timestamp_fails_closed():
    from datetime import datetime
    engine = _engine(regular_hours_only=True)
    engine._regular_hours_clock = lambda: datetime.fromisoformat("2026-10-01T15:30:00+00:00")  # in session now
    block = engine._regular_hours_block("SPY", "not-a-time")
    assert block and "unreadable timestamp" in block["clock"]
    assert engine._regular_hours_block("SPY") is None  # no timestamp at all: judged at the delivery time, in session


def test_an_alert_from_an_earlier_session_is_rejected_even_when_delivered_in_session():
    engine = _engine(regular_hours_only=True)
    decision = _decision(engine, "2026-10-01T19:55:00Z", clock="2026-10-02T13:35:00Z")  # Thu 15:55 alert, delivered Fri 09:35
    assert decision["status"] == "rejected" and decision["reason"].startswith("outside_regular_hours:")


def test_a_broker_without_a_calendar_is_limited_to_weekday_regular_hours():
    from datetime import datetime
    engine = TradingViewWebhookEngine(_config(regular_hours_only=True))

    class NoCalendar:
        def is_configured(self):
            return False

    engine.broker = NoCalendar()  # like the Robinhood adapter: no get_calendar_raw
    engine._regular_hours_clock = lambda: datetime.fromisoformat("2026-10-01T15:30:00+00:00")
    assert engine._regular_hours_block("SPY") is None
    engine._regular_hours_clock = lambda: datetime.fromisoformat("2026-10-01T20:30:00+00:00")
    assert engine._regular_hours_block("SPY") is not None


def test_a_generated_signal_is_not_judged_at_its_bar_start():
    from bot.core.types import Side, Signal
    engine = _engine(regular_hours_only=True)
    from datetime import datetime
    engine._regular_hours_clock = lambda: datetime.fromisoformat("2026-10-01T14:05:00+00:00")  # 10:05 ET
    signal = Signal("SPY", Side.BUY, "elephant_bar", {"entry_price": 500, "stop_price": 498, "order_type": "limit",
                                                      "timestamp": "2026-10-01T13:00:00+00:00"})  # the 09:00 bar's start
    decision = engine._build_order_decision(signal, "alert-3")
    assert not str(decision.reason).startswith("outside_regular_hours")


def _block_after(engine, allowed_calls):
    calls = {"n": 0}

    def block(symbol, timestamp=None, **_kw):
        calls["n"] += 1
        return None if calls["n"] <= allowed_calls else {"clock": "Thu 16:00:03 ET", "allowed": "x"}

    engine._regular_hours_block = block


def test_the_clock_is_checked_again_right_before_the_broker_call(monkeypatch):
    engine = _engine(regular_hours_only=True)
    submitted = []
    monkeypatch.setattr(engine, "_execute_orders", lambda: True)
    monkeypatch.setattr(engine, "_requires_order_approval", lambda: False)
    monkeypatch.setattr(engine.bullwarden, "entry_allowed", lambda *a, **k: {"allowed": True})
    monkeypatch.setattr(engine.broker, "submit_order_payload", lambda payload: submitted.append(payload) or {"id": "x"})
    _block_after(engine, 2)  # the alert-time and submission-time checks pass; the last look, after the slow steps, fails
    decision = engine.handle_payload(_signal("2026-10-01T19:59:58Z"), path_token="test-secret")["decisions"][0]
    assert decision["status"] == "rejected" and decision["reason"].startswith("outside_regular_hours:") and not submitted


def test_the_approval_callback_checks_the_clock_too(monkeypatch):
    import pytest
    engine = _engine(regular_hours_only=True)
    monkeypatch.setattr(engine, "_authorize_approval_token", lambda token: {"ok": True})
    monkeypatch.setattr(engine, "_execute_orders", lambda: True)
    monkeypatch.setattr(engine, "_paper_broker_endpoint", lambda: True)
    monkeypatch.setattr(engine.journal, "get_pending_order", lambda approval_id: {"symbol": "SPY", "order_payload": {}})
    monkeypatch.setattr(engine, "_session_lock_entry_state", lambda *a, **k: {"entry_allowed": True})
    monkeypatch.setattr(engine.bullwarden, "entry_allowed", lambda *a, **k: {"allowed": True})
    monkeypatch.setattr(engine.journal, "approve_pending_order", lambda approval_id, phrase, submitter: submitter({"symbol": "SPY"}))
    _block_after(engine, 1)  # the up-front check passes; the callback's own check, after Bull Warden, fails
    with pytest.raises(RuntimeError, match="outside_regular_hours"):
        engine.approve_pending_order("abc", "phrase", "token")


def test_a_generated_signal_from_an_earlier_session_is_rejected():
    from datetime import datetime
    from bot.core.types import Side, Signal
    engine = _engine(regular_hours_only=True)
    engine._regular_hours_clock = lambda: datetime.fromisoformat("2026-10-01T14:05:00+00:00")  # Thu 10:05 ET
    signal = Signal("SPY", Side.BUY, "elephant_bar", {"entry_price": 500, "stop_price": 498, "order_type": "limit",
                                                      "timestamp": "2026-09-30T19:45:00+00:00"})  # yesterday's 15:45 bar
    decision = engine._build_order_decision(signal, "alert-4")
    assert decision.status == "rejected" and decision.reason.startswith("outside_regular_hours:")
