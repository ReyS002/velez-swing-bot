from bot.brokers.tradovate import TradovateBroker, TradovateConfig
from bot.webhook_server import TradingViewWebhookEngine


def _engine_config():
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
        "event_filter": {"enabled": False},
        "scanner": {"symbols": ["MES"]},
        "symbols": [{"symbol": "MES", "type": "future", "contract_multiplier": 5, "session": "full"}],
        "velez_strategy": {},
    }


def test_tradingview_continuous_futures_symbol_normalizes_to_root_allowlist():
    engine = TradingViewWebhookEngine(_engine_config())

    result = engine.handle_payload(
        {
            "mode": "signal",
            "symbol": "CME_MINI:MES1!",
            "side": "buy",
            "play": "elephant_bar",
            "order_type": "market",
            "entry_price": 5000,
            "stop_price": 4995,
            "timestamp": "2026-01-01T14:30:00Z",
        },
        path_token="test-secret",
    )

    assert result["ok"] is True
    decision = result["decisions"][0]
    assert decision["symbol"] == "MES"
    assert decision["order_payload"]["symbol"] == "MES"


def test_tradovate_payload_uses_configurable_futures_symbol_mapping(monkeypatch):
    monkeypatch.setenv("TRADOVATE_SYMBOL_MAP", '{"MES":"MESU6","MGC":"MGCZ6"}')
    broker = TradovateBroker(
        TradovateConfig(username="user", password="pass", app_id="app", client_secret="secret")
    )
    monkeypatch.setattr(broker, "check_prop_trade_allowed", lambda: (True, "symbol_mapping_test"))

    payload = broker.build_entry_payload(
        symbol="CME_MINI:MES1!",
        side="buy",
        qty=1,
        order_type="market",
        entry_price=None,
        stop_price=4995,
    )

    assert payload["symbol"] == "MESU6"
    assert broker.tradovate_symbol("COMEX_MINI:MGC1!") == "MGCZ6"
