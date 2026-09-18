from datetime import datetime, timezone

from bot.core.session_lock import (
    evaluate_session_lock,
    read_session_lock,
    session_scope,
    update_session_lock,
    update_settings_value,
)
from bot.core.types import Side, Signal
from bot.webhook_server import TradingViewWebhookEngine


def test_session_windows_use_iana_timezones_and_dynamic_dst_overlap():
    london_open = evaluate_session_lock(
        "london",
        asset_type="forex",
        now=datetime(2026, 3, 30, 7, 30, tzinfo=timezone.utc),
    )
    assert london_open["entry_allowed"] is True

    us_cash_open = evaluate_session_lock(
        "us_cash",
        asset_type="equity",
        now=datetime(2026, 7, 6, 13, 30, tzinfo=timezone.utc),
    )
    us_cash_closed = evaluate_session_lock(
        "us_cash",
        asset_type="equity",
        now=datetime(2026, 7, 6, 20, 0, tzinfo=timezone.utc),
    )
    assert us_cash_open["entry_allowed"] is True
    assert us_cash_closed["lock_reason"] == "session_locked:us_cash"

    overlap_open = evaluate_session_lock(
        "london_new_york_overlap",
        asset_type="forex",
        now=datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc),
    )
    overlap_closed = evaluate_session_lock(
        "london_new_york_overlap",
        asset_type="forex",
        now=datetime(2026, 3, 16, 17, 0, tzinfo=timezone.utc),
    )
    assert overlap_open["entry_allowed"] is True
    assert overlap_closed["lock_reason"] == "session_locked:london_new_york_overlap"


def test_session_lock_enforces_asset_scope_and_all_defers_to_broker():
    asia_equity = evaluate_session_lock(
        "asia",
        asset_type="equity",
        now=datetime(2026, 1, 5, 0, 30, tzinfo=timezone.utc),
    )
    asia_fx = evaluate_session_lock(
        "asia",
        asset_type="fx",
        now=datetime(2026, 1, 5, 0, 30, tzinfo=timezone.utc),
    )
    all_hours = evaluate_session_lock("all", asset_type="equity")
    assert asia_equity["lock_reason"] == "session_locked:asia"
    assert asia_fx["entry_allowed"] is True
    assert all_hours["entry_allowed"] is True


def test_settings_updates_are_atomic_and_keep_each_bot_scope(tmp_path):
    path = tmp_path / "trading_bull_settings.json"
    update_settings_value(path, "trading_mode", "dual")
    update_session_lock(path, "velez_intraday", "london")
    update_session_lock(path, "velez_swing", "us_cash")

    assert read_session_lock(path, "velez_intraday")["selection"] == "london"
    assert read_session_lock(path, "velez_swing")["selection"] == "us_cash"
    assert '"trading_mode": "dual"' in path.read_text(encoding="utf-8")
    assert session_scope({"top_down": {"profile": "velez_intraday"}}, "velez_swing") == "velez_swing"


def test_corrupt_settings_fail_closed_for_entries(tmp_path):
    path = tmp_path / "trading_bull_settings.json"
    path.write_text("not-json", encoding="utf-8")
    stored = read_session_lock(path, "velez_swing")
    state = evaluate_session_lock(
        stored["selection"],
        asset_type="equity",
        settings_valid=stored["settings_valid"],
        settings_status=stored["settings_status"],
        settings_error=stored.get("settings_error"),
    )
    assert state["lock_reason"] == "session_locked:settings_unavailable"


def test_swing_entry_guard_records_a_session_locked_decision(monkeypatch):
    config = {
        "portfolio": {"initial_cash": 100000},
        "risk": {"risk_per_trade": 0.005, "max_open_positions": 3, "max_stop_pct": 0.1},
        "webhook": {"auth_required": True, "secret": "test-secret", "execute_orders": False, "paper_only": True},
        "event_filter": {"enabled": False},
        "scanner": {"enabled": False, "symbols": []},
        "symbols": [{"symbol": "SPY", "contract_multiplier": 1}],
        "velez_strategy": {},
    }
    engine = TradingViewWebhookEngine(config)
    monkeypatch.setattr(
        engine,
        "_session_lock_entry_state",
        lambda *_args, **_kwargs: {"entry_allowed": False, "lock_reason": "session_locked:asia"},
    )

    decision = engine._build_order_decision(
        Signal(
            symbol="SPY",
            side=Side.BUY,
            reason="test",
            metadata={"play": "elephant_bar", "entry_price": 500, "stop_price": 498, "order_type": "market"},
        ),
        "session-lock-test",
    )

    assert decision.status == "rejected"
    assert decision.reason == "session_locked:asia"
