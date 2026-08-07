from __future__ import annotations

from datetime import datetime, timedelta, timezone

from bot.core.top_down_brain import build_top_down_state
from bot.core.types import Bar
from bot.webhook_server import TradingViewWebhookEngine


def bars(start: float, step: float, count: int = 260) -> list[Bar]:
    now = datetime(2026, 8, 7, tzinfo=timezone.utc)
    return [
        Bar(
            timestamp=now - timedelta(days=count - index),
            open=start + step * index - 0.2,
            high=start + step * index + 0.5,
            low=start + step * index - 0.5,
            close=start + step * index,
            volume=1_000_000 + index,
        )
        for index in range(count)
    ]


def config() -> dict:
    return {
        "portfolio": {"initial_cash": 100000},
        "broker": {"sim": {"enabled": True}},
        "webhook": {"auth_required": False, "execute_orders": False, "paper_only": False},
        "scanner": {"enabled": False},
        "risk": {
            "risk_per_trade": 0.005,
            "max_dollar_risk_per_trade": 1000,
            "max_daily_loss_pct": 0.02,
            "max_open_positions": 7,
            "max_stop_pct": 0.05,
            "max_order_qty": 10000,
            "max_leverage": 2.0,
        },
        "strategy": {"correlation": {"sector_groups": {"semiconductors": ["NVDA"], "indices": ["SPY", "QQQ", "IWM"]}}},
        "velez_strategy": {"trifecta": {"enabled": False}, "lower_tf_filters": {"enabled": False}},
        "top_down": {"enabled": True, "mode": "advisory", "profile": "velez_swing"},
    }


def test_swing_top_down_brain_scores_daily_weekly_and_sector():
    state = build_top_down_state(
        config(),
        {"SPY": bars(100, 1), "QQQ": bars(100, 1.2), "IWM": bars(100, 0.8), "NVDA": bars(90, 1.5)},
        symbol="NVDA",
        play="elephant_bar",
        side="buy",
        confluence={"enabled": True, "action": "full_size", "reason": "trifecta_higher_timeframes_aligned", "signal_timeframe": "60"},
    )
    assert state["daily_bias"]["label"] == "bullish"
    assert state["weekly_bias"]["label"] == "bullish"
    assert state["sector"]["name"] == "semiconductors"
    assert state["strategy_activation"]["status"] == "active"


def test_swing_dashboard_has_cached_top_down_without_fetching(monkeypatch):
    engine = TradingViewWebhookEngine(config())
    monkeypatch.setattr(engine, "_positions_snapshot", lambda: ([], None))
    state = engine.dashboard_state()
    assert state["top_down"]["status"] == "not_loaded"


def test_swing_order_decision_includes_top_down_metadata(monkeypatch):
    engine = TradingViewWebhookEngine(config())
    top_down = {
        "ok": True,
        "mode": "advisory",
        "strategy_activation": {"status": "active", "executable": True, "size_multiplier": 1.0},
        "readback": "swing top-down active",
    }
    monkeypatch.setattr(engine, "top_down_state_payload", lambda **kwargs: top_down)
    result = engine._handle_signal_payload(
        {
            "symbol": "NVDA",
            "side": "buy",
            "entry_price": 100,
            "stop_price": 98,
            "play": "elephant_bar",
            "timeframe": "60",
        },
        "swing-td-test",
        dry_run=True,
    )
    assert result.status == "diagnostic"
    assert result.metadata["top_down"]["readback"] == "swing top-down active"
