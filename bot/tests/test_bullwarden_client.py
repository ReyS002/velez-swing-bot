from bot.core.bullwarden import BullWardenClient


class FakeBroker:
    def get_account(self):
        return {"equity": "50000", "last_equity": "50100"}


class FakeResponse:
    status_code = 200

    def json(self):
        return {"ok": True, "allowed": False, "reason": "daily_loss_buffer"}


def test_disabled_client_never_calls_broker(monkeypatch):
    monkeypatch.delenv("BULLWARDEN_ENABLED", raising=False)
    result = BullWardenClient().entry_allowed(None, source="test")
    assert result["allowed"] is True
    assert result["active"] is False


def test_enabled_client_relays_enforced_block(monkeypatch):
    monkeypatch.setenv("BULLWARDEN_ENABLED", "true")
    monkeypatch.setenv("BULLWARDEN_API_KEY", "test-key")
    monkeypatch.setenv("BULLWARDEN_ACCOUNT_ID", "test-account")
    monkeypatch.setattr("bot.core.bullwarden.requests.post", lambda *args, **kwargs: FakeResponse())
    result = BullWardenClient().entry_allowed(FakeBroker(), source="test", order_ref="order-1")
    assert result["allowed"] is False
    assert result["reason"] == "daily_loss_buffer"
