import base64
import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from bot.core.types import Bar
from bot.webhook_server import TradingViewWebhookEngine, create_app


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
    assert decision["qty"] == 62
    assert decision["metadata"]["lot_plan"]["lots"] == 1
    assert decision["metadata"]["lot_plan"]["effective_risk_budget"] == 125
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


def test_velez_lot_conviction_ladder_sizes_power_locations_and_caps_chased_setups():
    engine = TradingViewWebhookEngine(webhook_config())

    power = engine.handle_payload(
        {
            "mode": "signal",
            "symbol": "SPY",
            "side": "buy",
            "play": "elephant_bar",
            "order_type": "market",
            "entry_price": 500,
            "stop_price": 498,
            "location": "location_3_near_200_sma",
            "body_mult": 2.5,
        },
        path_token="test-secret",
    )["decisions"][0]

    assert power["metadata"]["lot_plan"]["lots"] == 4
    assert power["metadata"]["lot_plan"]["effective_risk_budget"] == 500
    assert power["qty"] == 250

    capped = engine.handle_payload(
        {
            "mode": "signal",
            "symbol": "SPY",
            "side": "buy",
            "play": "elephant_bar",
            "order_type": "market",
            "entry_price": 500,
            "stop_price": 498,
            "location": "location_3_near_200_sma",
            "body_mult": 2.5,
            "chased": True,
        },
        path_token="test-secret",
    )["decisions"][0]

    assert capped["metadata"]["lot_plan"]["lots"] == 2
    assert capped["metadata"]["lot_plan"]["effective_risk_budget"] == 250
    assert capped["qty"] == 125


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


def test_dashboard_auth_protects_dashboard_and_api_when_enabled(monkeypatch):
    monkeypatch.setenv("VELEZ_DASHBOARD_AUTH_ENABLED", "true")
    monkeypatch.setenv("VELEZ_DASHBOARD_USERNAME", "desk")
    monkeypatch.setenv("VELEZ_DASHBOARD_PASSWORD", "secret-pass")

    client = TestClient(create_app(webhook_config()))

    assert client.get("/health").status_code == 200
    assert client.get("/dashboard").status_code == 401
    assert client.get("/api/dashboard/state").status_code == 401

    token = base64.b64encode(b"desk:secret-pass").decode("ascii")
    response = client.get("/api/dashboard/state", headers={"Authorization": f"Basic {token}"})

    assert response.status_code == 200
    assert response.json()["dashboard_version"] == "v6.21"


def test_dashboard_auth_can_stay_disabled_for_local_development(monkeypatch):
    monkeypatch.delenv("VELEZ_DASHBOARD_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("VELEZ_DASHBOARD_USERNAME", raising=False)
    monkeypatch.delenv("VELEZ_DASHBOARD_PASSWORD", raising=False)

    client = TestClient(create_app(webhook_config()))

    assert client.get("/api/dashboard/state").status_code == 200


def test_notification_test_endpoint_dispatches_configured_target(monkeypatch, tmp_path):
    notify_file = tmp_path / "notification-tests.jsonl"
    monkeypatch.setenv("VELEZ_NOTIFY_FILE", str(notify_file))

    client = TestClient(create_app(webhook_config()))
    response = client.post("/api/notifications/test", json={"channel": "all"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert "file" in payload["targets"]
    assert "notification_test" in notify_file.read_text()


def test_vps_scanner_warms_without_trading_old_bars(monkeypatch):
    config = webhook_config()
    config["scanner"] = {
        "enabled": True,
        "auto_submit": False,
        "timeframe": "1Min",
        "history_bars": 260,
        "closed_bar_delay_seconds": 0,
    }
    engine = TradingViewWebhookEngine(config)
    base = datetime.now(timezone.utc) - timedelta(minutes=320)
    bars = [
        Bar(
            timestamp=base + timedelta(minutes=index),
            open=100 + index * 0.01,
            high=100.2 + index * 0.01,
            low=99.8 + index * 0.01,
            close=100.05 + index * 0.01,
            volume=1000,
        )
        for index in range(260)
    ]
    monkeypatch.setattr(engine, "_fetch_stock_bars", lambda symbol: bars)

    status = engine.scanner_scan_once()

    assert status["warmed_symbols"] == 1
    assert status["signals_found"] == 0
    assert engine.journal.latest_decisions(limit=1) == []
    assert engine.scanner_public_status()["enabled"] is True


def test_polygon_futures_adapter_maps_contracts_and_bars(monkeypatch):
    config = webhook_config()
    config["scanner"] = {
        "enabled": True,
        "auto_submit": False,
        "timeframe": "1Min",
        "futures_provider": "polygon",
        "futures_contracts": {"ES": "ESM6"},
    }
    config["symbols"] = [{"symbol": "ES", "type": "future", "contract_multiplier": 50}]
    monkeypatch.setenv("POLYGON_API_KEY", "polygon-test-key")
    engine = TradingViewWebhookEngine(config)

    calls = []

    def fake_polygon(path, *, params):
        calls.append((path, params))
        return {
            "results": [
                {
                    "window_start": 1_756_000_000_000_000_000,
                    "open": 5000,
                    "high": 5005,
                    "low": 4998,
                    "close": 5002,
                    "volume": 12,
                }
            ]
        }

    monkeypatch.setattr(engine, "_polygon_request", fake_polygon)

    bars = engine._fetch_scanner_bars(symbol="ES", asset_type="future")

    assert calls[0][0] == "/futures/vX/aggs/ESM6"
    assert calls[0][1]["resolution"] == "1min"
    assert bars[0].close == 5002
    assert bars[0].volume == 12
