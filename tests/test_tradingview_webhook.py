import json

from bot.webhook_server import TradingViewWebhookEngine


def webhook_config():
    return {
        "portfolio": {"initial_cash": 100000},
        "risk": {
            "risk_per_trade": 0.005,
            "max_dollar_risk_per_trade": 1000,
            "max_daily_loss_pct": 0.02,
            "max_consecutive_losses": 3,
            "max_open_positions": 3,
            "max_leverage": 2.0,
            "max_order_qty": 10000,
            "max_stop_pct": 0.1,
        },
        "webhook": {
            "auth_required": True,
            "secret": "test-secret",
            "execute_orders": False,
            "paper_only": True,
            "time_in_force": "day",
        },
        "symbols": [{"symbol": "SPY", "contract_multiplier": 1}],
        "velez_strategy": {},
    }


def test_tradingview_signal_webhook_proposes_paper_order_without_execution():
    config = webhook_config()
    engine = TradingViewWebhookEngine(config)

    result = engine.handle_payload(
        {
            "mode": "signal",
            "symbol": "SPY",
            "side": "buy",
            "play": "elephant_bar",
            "order_type": "market",
            "entry_price": 500,
            "stop_price": 498,
            "timestamp": "2026-01-01T14:30:00Z",
        },
        path_token="test-secret",
    )

    assert result["ok"]
    decision = result["decisions"][0]
    assert decision["status"] == "proposed"
    assert decision["qty"] == 250
    assert decision["order_payload"]["order_class"] == "oto"
    assert decision["order_payload"]["stop_loss"]["stop_price"] == "498.00"


def test_tradingview_webhook_rejects_bad_secret():
    config = {
        "risk": {"max_consecutive_losses": 3, "max_open_positions": 3, "max_daily_loss_pct": 0.02},
        "webhook": {"auth_required": True, "secret": "right-secret"},
    }
    engine = TradingViewWebhookEngine(config)

    result = engine.handle_payload({"mode": "signal", "symbol": "SPY"}, path_token="wrong")

    assert not result["ok"]
    assert result["decisions"][0]["reason"] == "invalid_webhook_secret"


def test_dashboard_state_tracks_recent_decisions_without_secrets():
    config = webhook_config()
    engine = TradingViewWebhookEngine(config)

    engine.handle_payload(
        {
            "mode": "signal",
            "symbol": "SPY",
            "side": "sell",
            "play": "bear_180",
            "order_type": "market",
            "entry_price": 500,
            "stop_price": 502,
            "timestamp": "2026-01-01T14:30:00Z",
            "secret": "test-secret",
        }
    )

    state = engine.dashboard_state()
    serialized = json.dumps(state)

    assert state["recent_decisions"][0]["symbol"] == "SPY"
    assert state["recent_decisions"][0]["side"] == "sell"
    assert state["recent_decisions"][0]["stop_price"] == "502.00"
    assert state["guardrails"]["auth_required"] is True
    assert "test-secret" not in serialized
    assert "client_order_id" not in serialized
