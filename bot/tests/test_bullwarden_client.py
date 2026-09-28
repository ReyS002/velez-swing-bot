from bot.core.bullwarden import BullWardenClient


class FakeBroker:
    def get_account(self):
        return {"equity": "50000", "last_equity": "50100"}


class FakeResponse:
    status_code = 200

    def json(self):
        return {"ok": True, "allowed": False, "submit_eligible": False, "reason": "daily_loss_buffer", "review_action_label": "Conditions Not Met"}


def test_disabled_client_never_calls_broker(monkeypatch):
    monkeypatch.delenv("BULLWARDEN_ENABLED", raising=False)
    result = BullWardenClient().entry_allowed(None, source="test")
    assert result["allowed"] is True
    assert result["active"] is False


def test_enabled_client_relays_enforced_block(monkeypatch):
    monkeypatch.setenv("BULLWARDEN_ENABLED", "true")
    monkeypatch.setenv("BULLWARDEN_API_KEY", "test-key")
    monkeypatch.setenv("BULLWARDEN_ACCOUNT_ID", "test-account")
    captured = {}
    def post(*args, **kwargs):
        captured.update(kwargs["json"])
        return FakeResponse()
    monkeypatch.setattr("bot.core.bullwarden.requests.post", post)
    result = BullWardenClient().entry_allowed(
        FakeBroker(), source="test", order_ref="order-1",
        trade={
            "symbol": "MES", "direction": "buy", "quantity": 1,
            "entry_price": 5000, "stop_price": 4998, "target_price": 5004,
            "point_value": 5, "setup_type": "elephant_bar", "profile_key": "test_50k",
            "rules_version": "2026-08-21", "signal_id": "signal-1",
            "signal_timestamp": "2026-08-21T14:30:00Z", "asset_class": "futures", "mode": "paper",
        },
    )
    assert result["allowed"] is False
    assert result["reason"] == "daily_loss_buffer"
    assert captured["symbol"] == "MES"
    assert captured["commit_intent"] is True


def test_enabled_client_fails_closed_when_account_or_service_is_unavailable(monkeypatch):
    monkeypatch.setenv("BULLWARDEN_ENABLED", "true")
    monkeypatch.setenv("BULLWARDEN_API_KEY", "test-key")
    monkeypatch.setenv("BULLWARDEN_ACCOUNT_ID", "test-account")
    monkeypatch.setattr("bot.core.bullwarden.requests.post", lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError()))
    result = BullWardenClient().entry_allowed(FakeBroker(), source="test", order_ref="order-1", trade={})
    assert result["allowed"] is False
    assert result["reason"].startswith("bullwarden_unavailable")
