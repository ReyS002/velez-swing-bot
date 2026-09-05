import base64
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from bot.webhook_server import create_app


class ReadOnlyBroker:
    def __init__(self):
        self.config = SimpleNamespace(base_url="https://paper-api.alpaca.markets")
        self.submitted = []

    def is_configured(self):
        return True

    def validate_connection(self):
        return {"ok": True, "account_status": "ACTIVE", "paper": True}

    def get_account(self):
        return {"equity": "100000", "last_equity": "100000", "buying_power": "200000"}

    def get_positions_raw(self):
        return []

    def get_orders_raw(self, **kwargs):
        return []

    def submit_order_payload(self, payload):
        self.submitted.append(payload)
        raise AssertionError("roadmap advisory API attempted to submit")


def config():
    return {
        "portfolio": {"initial_cash": 100000},
        "risk": {
            "risk_per_trade": 0.005,
            "max_dollar_risk_per_trade": 1000,
            "max_daily_loss_pct": 0.02,
            "max_consecutive_losses": 3,
            "max_open_positions": 5,
            "max_total_open_risk_pct": 0.02,
            "max_leverage": 2,
            "max_order_qty": 10000,
            "circuit_breaker_atr_pct": 8,
        },
        "webhook": {"auth_required": False, "execute_orders": False, "paper_only": True},
        "event_filter": {"enabled": False},
        "scanner": {"enabled": False},
        "bull_mentor": {"enabled": True, "minimum_performance_sample": 5},
        "symbols": [{"symbol": "SPY", "type": "equity", "contract_multiplier": 1}],
        "velez_strategy": {},
    }


def app_with_broker():
    app = create_app(config())
    broker = ReadOnlyBroker()
    app.state.engine.broker = broker
    app.state.engine.calendar.broker = broker
    app.state.engine.market_quote_payload = lambda symbol: {
        "ok": True,
        "symbol": symbol,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "spread_bps": 3,
        "source": "test_broker_quote",
    }
    return app, broker


def test_entitlements_enforce_pro_routes_server_side_and_keep_safety_core(monkeypatch):
    monkeypatch.setenv("VELEZ_DASHBOARD_TIER", "core")
    app, _ = app_with_broker()
    client = TestClient(app)

    entitlements = client.get("/api/entitlements")
    pro = client.get("/api/pro/bootstrap")
    mentor = client.get("/api/mentor/today")
    safety = client.get("/api/risk/status")

    assert entitlements.status_code == 200
    assert entitlements.json()["features"]["pro_console"]["allowed"] is False
    assert pro.status_code == 403 and pro.json()["reason"] == "feature_not_entitled"
    assert mentor.status_code == 403
    assert safety.status_code == 200
    assert safety.json()["guardrails"]["paper_only"] is True


def test_readiness_and_planner_are_explainable_and_planner_cannot_submit():
    app, broker = app_with_broker()
    engine = app.state.engine
    engine.journal.record_decision(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "alert_ref": "API-READY",
            "status": "proposed",
            "reason": "execution_disabled",
            "symbol": "SPY",
            "side": "buy",
            "play": "elephant_bar",
            "entry_price": 100,
            "stop_price": 99,
            "take_profit_price": 102,
            "qty": 500,
            "confidence_receipt": {"score": 90, "summary": "Verified API fixture."},
        }
    )
    client = TestClient(app)

    readiness = client.get("/api/readiness?alert_ref=API-READY&advanced=true")
    plan = client.post(
        "/api/planner/preview",
        json={
            "symbol": "SPY",
            "direction": "buy",
            "planned_entry": 100,
            "stop": 99,
            "target_one": 102,
            "target_two": 103,
            "invalidation_reason": "Trigger-bar structure fails.",
        },
    )

    assert readiness.status_code == 200
    assert readiness.json()["components"]
    assert all(item["reason"] and item["why_this_matters"] for item in readiness.json()["components"])
    assert plan.status_code == 200
    assert plan.json()["can_submit"] is False
    assert plan.json()["broker_read_only"] is True
    assert broker.submitted == []


def test_private_notes_and_structured_reviews_are_same_origin_protected():
    app, _ = app_with_broker()
    engine = app.state.engine
    engine.journal.record_decision(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "alert_ref": "REVIEW-1",
            "status": "proposed",
            "symbol": "SPY",
            "side": "buy",
            "play": "elephant_bar",
            "entry_price": 100,
            "stop_price": 99,
        }
    )
    client = TestClient(app)

    blocked = client.put("/api/notes/SPY", headers={"Origin": "https://evil.example"}, json={"thesis": "unsafe origin"})
    saved = client.put(
        "/api/notes/SPY",
        headers={"Origin": "http://testserver"},
        json={"thesis": "Verified operator thesis", "key_levels": [{"label": "Prior high", "price": 105}]},
    )
    review = client.put(
        "/api/journal/structured-review/REVIEW-1",
        headers={"Origin": "http://testserver"},
        json={"strategy": "elephant_bar", "rule_followed": True, "stop_followed": True, "authorized_setup": True},
    )

    assert blocked.status_code == 403 and blocked.json()["reason"] == "cross_site_mutation_blocked"
    assert saved.status_code == 200 and saved.json()["private"] is True
    assert client.get("/api/notes/SPY").json()["note"]["thesis"] == "Verified operator thesis"
    assert review.status_code == 200
    assert client.get("/api/journal/structured-review/REVIEW-1").json()["review"]["stop_followed"] is True


def test_dashboard_auth_and_security_headers_cover_new_private_routes(monkeypatch):
    monkeypatch.setenv("VELEZ_DASHBOARD_AUTH_ENABLED", "true")
    monkeypatch.setenv("VELEZ_DASHBOARD_USERNAME", "owner")
    monkeypatch.setenv("VELEZ_DASHBOARD_PASSWORD", "test-password")
    app, _ = app_with_broker()
    client = TestClient(app)
    token = base64.b64encode(b"owner:test-password").decode()

    anonymous = client.get("/api/notes/SPY")
    authenticated = client.get("/api/notes/SPY", headers={"Authorization": f"Basic {token}"})

    assert anonymous.status_code == 401
    assert authenticated.status_code == 200
    assert authenticated.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in authenticated.headers["content-security-policy"]
    assert "https://www.tradingview-widget.com" in authenticated.headers["content-security-policy"]


def test_market_playbook_annotations_missed_and_discipline_empty_states_are_honest():
    app, _ = app_with_broker()
    client = TestClient(app)

    playbook = client.get("/api/playbook?query=Elephant")
    annotations = client.get("/api/annotations?symbol=SPY")
    missed = client.get("/api/missed-trades")
    discipline = client.get("/api/discipline")

    assert playbook.status_code == 200 and playbook.json()["count"] == 1
    assert annotations.json()["levels"] == []
    assert annotations.json()["render_mode"] == "synchronized_adjacent_layer"
    assert missed.json()["items"] == []
    assert discipline.json()["score"] is None
    assert discipline.json()["label"] == "Insufficient evidence"
