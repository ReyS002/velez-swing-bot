import json

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from bot.webhook_server import AppleMusicTokenService


def test_apple_music_token_service_reports_missing_config(monkeypatch):
    for key in (
        "APPLE_MUSIC_TEAM_ID",
        "APPLE_MUSIC_KEY_ID",
        "APPLE_MUSIC_PRIVATE_KEY_PATH",
        "APPLE_MUSIC_TOKEN_ORIGINS",
        "VELEZ_PUBLIC_HOST",
        "VELEZ_PUBLIC_URL",
    ):
        monkeypatch.delenv(key, raising=False)

    result = AppleMusicTokenService().developer_token()

    assert result["ok"] is False
    assert result["reason"] == "not_configured"
    assert "APPLE_MUSIC_TEAM_ID" in result["missing"]
    assert "APPLE_MUSIC_KEY_ID" in result["missing"]
    assert "APPLE_MUSIC_PRIVATE_KEY_PATH" in result["missing"]


def test_apple_music_token_service_generates_es256_developer_token(monkeypatch, tmp_path):
    private_key = ec.generate_private_key(ec.SECP256R1())
    key_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_path = tmp_path / "AuthKey_8UA7B6SWHC.p8"
    key_path.write_bytes(key_bytes)

    monkeypatch.setenv("APPLE_MUSIC_TEAM_ID", "SH5BHDD8FB")
    monkeypatch.setenv("APPLE_MUSIC_KEY_ID", "8UA7B6SWHC")
    monkeypatch.setenv("APPLE_MUSIC_PRIVATE_KEY_PATH", str(key_path))
    monkeypatch.setenv("APPLE_MUSIC_TOKEN_TTL_HOURS", "12")
    monkeypatch.setenv("APPLE_MUSIC_TOKEN_ORIGINS", "https://velezbot.example.com")

    result = AppleMusicTokenService().developer_token()

    assert result["ok"] is True
    assert result["key_id_tail"] == "SWHC"
    assert result["team_id_tail"] == "D8FB"
    assert result["origin_locked"] is True

    token = result["developer_token"]
    header = jwt.get_unverified_header(token)
    payload = jwt.decode(token, options={"verify_signature": False})

    assert header["alg"] == "ES256"
    assert header["kid"] == "8UA7B6SWHC"
    assert payload["iss"] == "SH5BHDD8FB"
    assert payload["origin"] == ["https://velezbot.example.com"]
    assert payload["exp"] > payload["iat"]
    assert "PRIVATE KEY" not in json.dumps(result)
