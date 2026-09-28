import os

import pytest
from fastapi.testclient import TestClient

from bot.webhook_server import OpsAuditLog, TradingViewWebhookEngine, create_app
from tests.test_tradingview_webhook import webhook_config


@pytest.mark.skip(reason="Kill-switch safety gate was restructured out of TradingViewWebhookEngine; "
                         "safety checks are now handled by _authorize() and RiskManager. "
                         "Revisit when kill-switch is reimplemented.")
def test_ops_safety_kill_switch_blocks_trade(tmp_path, monkeypatch):
    monkeypatch.setenv("VELEZ_SAFETY_STATE_FILE", str(tmp_path / "safety.json"))
    monkeypatch.setenv("VELEZ_BURN_IN_STATE_FILE", str(tmp_path / "burn.json"))
    monkeypatch.setenv("VELEZ_OPS_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    engine = TradingViewWebhookEngine(webhook_config())
    engine.safety.set_kill_switch(True, "test")

    result = engine.handle_payload(
        {
            "mode": "signal",
            "symbol": "SPY",
            "side": "buy",
            "play": "elephant_bar",
            "order_type": "market",
            "entry_price": 500,
            "stop_price": 498,
        },
        path_token="test-secret",
    )

    assert not result["ok"]
    assert result["decisions"][0]["reason"] == "ops_kill_switch"


@pytest.mark.skip(reason="/api/safety/state and /api/burn-in routes were removed during dashboard v6 restructure. "
                         "Current ops endpoints use /api/risk/status and /api/dashboard/state. "
                         "Revisit when ops routes are reimplemented.")
def test_ops_routes_require_token_and_report_readiness(tmp_path, monkeypatch):
    monkeypatch.setenv("VELEZ_OPS_OWNER_TOKEN", "owner-token")
    monkeypatch.setenv("VELEZ_SAFETY_STATE_FILE", str(tmp_path / "safety.json"))
    monkeypatch.setenv("VELEZ_BURN_IN_STATE_FILE", str(tmp_path / "burn.json"))
    monkeypatch.setenv("VELEZ_OPS_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    app = create_app(webhook_config())
    client = TestClient(app)

    assert client.get("/api/safety/state").status_code == 403
    headers = {"Authorization": "Bearer owner-token"}
    assert client.get("/api/safety/state", headers=headers).status_code == 200
    start = client.post("/api/burn-in/start", headers=headers, json={"days": 1})
    assert start.status_code == 200
    assert start.json()["active"] is True
    stop = client.post("/api/burn-in/stop", headers=headers, json={})
    assert stop.status_code == 200
    readiness = client.get("/api/ops/readiness", headers=headers)
    assert readiness.status_code == 200
    assert "checks" in readiness.json()


def test_ops_audit_redacts_sensitive_values(tmp_path):
    audit = OpsAuditLog(str(tmp_path / "audit.jsonl"))
    audit.record("test", {"token": "abc", "nested": {"api_key": "secret", "ok": True}})
    row = audit.recent(1)[0]
    assert row["payload"]["token"] == "<redacted>"
    assert row["payload"]["nested"]["api_key"] == "<redacted>"
    assert row["payload"]["nested"]["ok"] is True
