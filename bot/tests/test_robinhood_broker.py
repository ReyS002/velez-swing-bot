from pathlib import Path

import pytest

from bot.brokers.robinhood import RobinhoodAgenticBroker, RobinhoodAgenticConfig, RobinhoodBrokerError


class Response:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def config(tmp_path: Path, *, protective_stops_verified=False):
    return RobinhoodAgenticConfig(
        bridge_url="http://127.0.0.1:8188",
        bridge_key="x" * 32,
        account_number="agentic-1",
        shadow_mode=True,
        execution_enabled=False,
        protective_stops_verified=protective_stops_verified,
        execution_gateway_url="http://bull-pilot:8080",
        execution_gateway_token="gateway-token",
    )


def order():
    return {"symbol": "SPY", "side": "buy", "qty": "1", "type": "limit", "limit_price": "500", "time_in_force": "day", "client_order_id": "velez-rh-test-1"}


def test_velez_prepares_broker_neutral_intent_without_robinhood_call(tmp_path, monkeypatch):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs["json"]))
        return Response({
            "prepared_intent_id": "prepared-1", "intent_fingerprint": "a" * 64,
            "approval_mode": "review_required", "state": "prepared",
        })

    monkeypatch.setattr("bot.brokers.robinhood.requests.post", post)
    result = RobinhoodAgenticBroker(config(tmp_path)).submit_order_payload(order())

    assert result["status"] == "prepared_review_required"
    assert [url for url, _ in calls] == ["http://bull-pilot:8080/internal/execution/prepare"]
    assert "account_id" not in calls[0][1]["payload"]
    assert "review_equity_order" not in str(calls)
    assert "place_equity_order" not in str(calls)


def test_shadow_mode_does_not_forward_rules_authorized_preparation_to_submit(tmp_path, monkeypatch):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs["json"]))
        if url.endswith("/prepare"):
            return Response({
                "prepared_intent_id": "prepared-2", "intent_fingerprint": "b" * 64,
                "approval_mode": "rules_authorized", "authorization_ref": "server-grant",
            })
        return Response({"status": "submitted", "result": {"status": "shadow_preview"}})

    monkeypatch.setattr("bot.brokers.robinhood.requests.post", post)
    result = RobinhoodAgenticBroker(config(tmp_path)).submit_order_payload(order())

    assert result["status"] == "prepared_review_required"
    assert len(calls) == 1
    assert calls[0][0].endswith("/internal/execution/prepare")


def test_velez_cannot_submit_an_unprepared_or_direct_robinhood_order(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("bot.brokers.robinhood.requests.post", lambda url, **kwargs: calls.append(url) or Response({}))
    broker = RobinhoodAgenticBroker(config(tmp_path))

    with pytest.raises(RobinhoodBrokerError, match="prepared_intent_reference_required"):
        broker.submit_prepared_order("", "", None)
    with pytest.raises(RobinhoodBrokerError, match="direct_robinhood_cancellation_disabled"):
        broker.cancel_order("broker-order-id")
    assert calls == []


def test_read_only_robinhood_calls_use_authenticated_account_number_schema(tmp_path, monkeypatch):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs["json"]))
        return Response({"ok": True, "result": {"isError": False, "structuredContent": {"data": {"total_value": "0", "buying_power": {"buying_power": "0"}}}}})

    monkeypatch.setattr("bot.brokers.robinhood.requests.post", post)
    account = RobinhoodAgenticBroker(config(tmp_path)).get_account()

    assert calls[0][0].endswith("/v1/tools/get_portfolio")
    assert calls[0][1]["arguments"] == {"account_number": "agentic-1"}
    assert account["buying_power"] == "0"


def test_protective_stop_entry_stays_blocked_until_schema_capability_is_verified(tmp_path, monkeypatch):
    monkeypatch.setattr("bot.brokers.robinhood.requests.post", lambda *args, **kwargs: Response({"prepared_intent_id": "prepared-stop", "intent_fingerprint": "s" * 64, "approval_mode": "review_required"}))
    broker = RobinhoodAgenticBroker(config(tmp_path, protective_stops_verified=False))
    protected = broker.build_entry_payload(
        symbol="SPY", side="buy", qty=1, order_type="limit", entry_price=500,
        stop_price=495, client_order_id="velez-rh-protected-1",
    )

    result = broker.submit_order_payload(protected)
    assert result["status"] == "prepared_review_required"


def test_fractional_long_intent_is_normalized_and_shadow_never_submits(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("bot.brokers.robinhood.requests.post", lambda url, **kwargs: calls.append((url, kwargs["json"])) or Response({"prepared_intent_id": "prepared-fractional", "intent_fingerprint": "f" * 64, "approval_mode": "rules_authorized"}))
    result = RobinhoodAgenticBroker(config(tmp_path)).submit_order_payload({**order(), "qty": "0.123456"})
    assert result["submitted"] is False
    assert calls[0][1]["payload"]["qty"] == "0.1235"
    assert len(calls) == 1


def test_direct_robinhood_placement_tool_is_unavailable(tmp_path):
    with pytest.raises(RobinhoodBrokerError, match="tool_not_allowed"):
        RobinhoodAgenticBroker(config(tmp_path))._call("place_equity_order", {})


def test_shadow_deployment_manifest_has_immutable_revision_and_required_locks():
    root = Path(__file__).resolve().parents[2]
    compose = (root / "bot/deploy/robinhood-shadow-compose.yml").read_text()
    dockerfile = (root / "bot/deploy/Dockerfile.webhook").read_text()
    assert "VELEZ_ROBINHOOD_IMAGE" in compose
    assert "VELEZ_ROBINHOOD_REVISION" in compose
    assert "VELEZ_BROKER: robinhood" in compose
    assert "VELEZ_ROBINHOOD_EXECUTION_ENABLED: \"false\"" in compose
    assert "/run/hermes-trading:/run/hermes-trading:ro" in compose
    assert "org.opencontainers.image.revision" in dockerfile
