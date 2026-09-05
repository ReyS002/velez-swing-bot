from __future__ import annotations

from datetime import datetime, timedelta, timezone

from bot.core.top_down_brain import build_top_down_state
from bot.core.types import Bar
from bot.webhook_server import TradingViewWebhookEngine


def bars(start: float, step: float, count: int = 90) -> list[Bar]:
    now = datetime(2026, 8, 7, tzinfo=timezone.utc)
    out = []
    for index in range(count):
        close = start + step * index
        out.append(
            Bar(
                timestamp=now - timedelta(days=count - index),
                open=close - 0.2,
                high=close + 0.5,
                low=close - 0.5,
                close=close,
                volume=1_000_000 + index,
            )
        )
    return out


def config() -> dict:
    return {
        "portfolio": {"initial_cash": 100000},
        "broker": {"sim": {"enabled": True}},
        "webhook": {"auth_required": False, "execute_orders": False, "paper_only": True},
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
        "strategy": {"correlation": {"sector_groups": {"semiconductors": ["NVDA", "AMD"], "indices": ["SPY", "QQQ", "IWM"]}}},
        "velez_strategy": {"lower_tf_filters": {"enabled": False}, "webhook_confluence": {"enabled": False}},
        "top_down": {"enabled": True, "mode": "advisory", "profile": "velez_intraday"},
        "bull_mentor": {"enabled": False},
        "mentor_operations": {"enabled": False},
    }


def test_top_down_brain_scores_bias_breadth_sector_and_activation():
    state = build_top_down_state(
        config(),
        {"SPY": bars(100, 1, 260), "QQQ": bars(100, 1.2, 260), "IWM": bars(100, 0.8, 260), "NVDA": bars(90, 1.5, 260)},
        symbol="NVDA",
        play="opening_gap_go",
        side="buy",
        confluence={"enabled": True, "action": "full_size", "reason": "all_available_higher_timeframes_aligned", "signal_timeframe": "5"},
    )
    assert state["daily_bias"]["label"] == "bullish"
    assert state["breadth"]["label"] == "supportive"
    assert state["sector"]["name"] == "semiconductors"
    assert state["strategy_activation"]["status"] == "active"


def test_dashboard_uses_cached_only_top_down_without_fetching(monkeypatch):
    engine = TradingViewWebhookEngine(config())
    monkeypatch.setattr(engine, "_positions_snapshot", lambda: ([], None))
    state = engine.dashboard_state()
    assert state["top_down"]["status"] == "not_loaded"
    assert state["top_down"]["enabled"] is True


def test_order_decision_includes_top_down_metadata(monkeypatch):
    engine = TradingViewWebhookEngine(config())
    top_down = {
        "ok": True,
        "mode": "advisory",
        "strategy_activation": {"status": "active", "executable": True, "size_multiplier": 1.0},
        "readback": "top-down active",
    }
    monkeypatch.setattr(engine, "top_down_state_payload", lambda **kwargs: top_down)
    signal_payload = {
        "symbol": "NVDA",
        "side": "buy",
        "entry_price": 100,
        "stop_price": 98,
        "play": "elephant_bar",
        "timeframe": "5",
    }
    result = engine._handle_signal_payload(signal_payload, "td-test", dry_run=True)
    assert result.status == "diagnostic"
    assert result.metadata["top_down"]["readback"] == "top-down active"
