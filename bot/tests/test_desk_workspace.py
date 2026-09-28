from types import SimpleNamespace

from bot.desk_workspace import broadcast_config, workspace_config


def test_video_configuration_is_explicit_and_never_exposes_credentials(monkeypatch):
    monkeypatch.delenv("DESK_BROADCAST_ENABLED", raising=False)
    monkeypatch.delenv("BULLPILOT_BROADCAST_ENABLED", raising=False)
    monkeypatch.setenv("DESK_BROADCAST_VIDEO_URL", "javascript:alert(1)")
    monkeypatch.setenv("DESK_BROADCAST_YOUTUBE_VIDEO_ID", "invalid-id")
    monkeypatch.setenv("DESK_BROADCAST_YOUTUBE_CHANNEL_URL", "https://untrusted.example/channel")
    value = broadcast_config()
    assert {key: value[key] for key in ("enabled", "preview", "video_url", "youtube_video_id", "youtube_channel_url")} == {"enabled": True, "preview": True, "video_url": "", "youtube_video_id": "", "youtube_channel_url": ""}
    assert value["default_channel"] == "bloomberg"
    assert next(c for c in value["channels"] if c["id"] == "academy")["kind"] == "coming-soon"
    monkeypatch.setenv("DESK_BROADCAST_VIDEO_URL", "https://media.example/briefing.mp4")
    assert broadcast_config()["preview"] is False
    monkeypatch.setenv("DESK_BROADCAST_ENABLED", "false")
    assert broadcast_config()["enabled"] is False


def test_workspace_identity_uses_selected_broker_and_keeps_secrets_private(monkeypatch):
    monkeypatch.setenv("BULLPILOT_BROKER_PROVIDER", "robinhood_mcp")
    monkeypatch.setenv("HERMES_ROBINHOOD_BRIDGE_KEY", "must-not-be-returned")
    request = SimpleNamespace(state=SimpleNamespace(dashboard_username="workspace-admin", dashboard_tier="pro"))
    result = workspace_config(request, object(), product="Velez Bot")
    assert result["broker_provider"] == "robinhood_mcp"
    assert result["authenticated"] is True
    assert result["tier"] == "pro"
    assert result["account_mode"] == "workspace"
    assert "must-not-be-returned" not in str(result)
    assert "workspace-admin" not in str(result)
