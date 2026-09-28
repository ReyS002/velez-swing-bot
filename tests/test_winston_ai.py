from bot.webhook_server import TradingViewWebhookEngine


def winston_config():
    return {
        "portfolio": {"initial_cash": 100000},
        "risk": {
            "risk_per_trade": 0.005,
            "max_dollar_risk_per_trade": 1000,
            "max_daily_loss_pct": 0.02,
            "max_open_positions": 3,
            "max_stop_pct": 0.1,
        },
        "webhook": {
            "auth_required": False,
            "execute_orders": False,
            "paper_only": True,
        },
        "symbols": [{"symbol": "SPY", "contract_multiplier": 1}],
        "velez_strategy": {},
    }


def clear_winston_env(monkeypatch):
    for name in (
        "WINSTON_LLM_PROVIDER",
        "WINSTON_LLM_BASE_URL",
        "WINSTON_LLM_MODEL",
        "WINSTON_LLM_API_KEY",
        "WINSTON_LLM_THINK",
        "WINSTON_TTS_PROVIDER",
        "WINSTON_TTS_BASE_URL",
        "WINSTON_TTS_API_KEY",
        "WINSTON_TTS_VOICE",
        "POCKETTTS_URL",
        "POCKETTTS_API_KEY",
        "POCKETTTS_DEFAULT_VOICE",
    ):
        monkeypatch.delenv(name, raising=False)


def test_winston_defaults_to_safe_local_rules(monkeypatch):
    clear_winston_env(monkeypatch)
    engine = TradingViewWebhookEngine(winston_config())

    status = engine.winston.status()
    result = engine.winston_reply("give me the risk")

    assert status["brain"]["provider"] == "winston_rule_based_v1"
    assert status["voice"]["provider"] == "browser"
    assert result["provider"] == "winston_rule_based_v1"
    assert result["llm_used"] is False
    assert "Risk is capped" in result["reply"]


def test_winston_trade_actions_are_guarded_before_llm(monkeypatch):
    clear_winston_env(monkeypatch)
    monkeypatch.setenv("WINSTON_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("WINSTON_LLM_MODEL", "gemma2-2b-local:latest")
    engine = TradingViewWebhookEngine(winston_config())

    result = engine.winston_reply("approve this buy order for 100 shares")

    assert result["provider"] == "winston_trade_guardrail_v1"
    assert result["llm_used"] is False
    assert "cannot submit" in result["reply"]


def test_winston_can_use_ollama_provider(monkeypatch):
    clear_winston_env(monkeypatch)
    monkeypatch.setenv("WINSTON_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("WINSTON_LLM_MODEL", "gemma2-2b-local:latest")
    engine = TradingViewWebhookEngine(winston_config())

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": "Winston online. The desk is calm and ready."}}

    def fake_post(url, json=None, timeout=None, headers=None):
        assert url.endswith("/api/chat")
        assert json["model"] == "gemma2-2b-local:latest"
        return FakeResponse()

    monkeypatch.setattr("bot.webhook_server.requests.post", fake_post)

    result = engine.winston_reply("what can you do")

    assert result["provider"] == "ollama"
    assert result["llm_used"] is True
    assert result["reply"] == "Winston online. The desk is calm and ready."


def test_winston_can_disable_ollama_thinking(monkeypatch):
    clear_winston_env(monkeypatch)
    monkeypatch.setenv("WINSTON_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("WINSTON_LLM_MODEL", "qwen3.5:2b")
    monkeypatch.setenv("WINSTON_LLM_THINK", "false")
    engine = TradingViewWebhookEngine(winston_config())

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": "Winston is online with guarded voice execution."}}

    def fake_post(url, json=None, timeout=None, headers=None):
        assert url.endswith("/api/chat")
        assert json["model"] == "qwen3.5:2b"
        assert json["think"] is False
        return FakeResponse()

    monkeypatch.setattr("bot.webhook_server.requests.post", fake_post)

    result = engine.winston_reply("status check")

    assert result["provider"] == "ollama"
    assert result["model"] == "qwen3.5:2b"
    assert result["reply"] == "Winston is online with guarded voice execution."


def test_winston_pockettts_speech_uses_openai_compatible_endpoint(monkeypatch):
    clear_winston_env(monkeypatch)
    monkeypatch.setenv("WINSTON_TTS_PROVIDER", "pockettts")
    monkeypatch.setenv("WINSTON_TTS_BASE_URL", "http://127.0.0.1:8018/v1")
    monkeypatch.setenv("WINSTON_TTS_API_KEY", "test-key")
    monkeypatch.setenv("WINSTON_TTS_VOICE", "jarvis-intro1")
    engine = TradingViewWebhookEngine(winston_config())

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "audio/mpeg"}
        content = b"fake-mp3"
        text = ""

    def fake_post(url, headers=None, json=None, timeout=None):
        assert url == "http://127.0.0.1:8018/v1/audio/speech"
        assert headers["Authorization"] == "Bearer test-key"
        assert json["voice"] == "jarvis-intro1"
        assert json["response_format"] == "mp3"
        return FakeResponse()

    monkeypatch.setattr("bot.webhook_server.requests.post", fake_post)

    result = engine.winston.synthesize_speech("hello from Winston")

    assert result["ok"] is True
    assert result["media_type"] == "audio/mpeg"
    assert result["content"] == b"fake-mp3"
