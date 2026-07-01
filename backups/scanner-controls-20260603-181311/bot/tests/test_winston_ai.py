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
        "WINSTON_LLM_THINKING",
        "WINSTON_LLM_REASONING_EFFORT",
        "WINSTON_LLM_EXTRA_BODY_JSON",
        "WINSTON_LLM_FALLBACK_PROVIDER",
        "WINSTON_LLM_FALLBACK_BASE_URL",
        "WINSTON_LLM_FALLBACK_MODEL",
        "WINSTON_LLM_FALLBACK_THINK",
        "WINSTON_TTS_PROVIDER",
        "WINSTON_TTS_BASE_URL",
        "WINSTON_TTS_API_KEY",
        "WINSTON_TTS_VOICE",
        "WINSTON_RESEARCH_LLM_PROVIDER",
        "WINSTON_RESEARCH_LLM_BASE_URL",
        "WINSTON_RESEARCH_LLM_MODEL",
        "WINSTON_RESEARCH_LLM_API_KEY",
        "WINSTON_RESEARCH_THINK",
        "WINSTON_RESEARCH_THINKING",
        "WINSTON_RESEARCH_REASONING_EFFORT",
        "WINSTON_RESEARCH_MAX_TOKENS",
        "WINSTON_RESEARCH_FALLBACK_PROVIDER",
        "WINSTON_RESEARCH_FALLBACK_BASE_URL",
        "WINSTON_RESEARCH_FALLBACK_MODEL",
        "WINSTON_RESEARCH_FALLBACK_THINK",
        "WINSTON_DEEP_RESEARCH_LLM_PROVIDER",
        "WINSTON_DEEP_RESEARCH_LLM_BASE_URL",
        "WINSTON_DEEP_RESEARCH_LLM_MODEL",
        "WINSTON_DEEP_RESEARCH_LLM_API_KEY",
        "WINSTON_DEEP_RESEARCH_THINK",
        "WINSTON_DEEP_RESEARCH_THINKING",
        "WINSTON_DEEP_RESEARCH_REASONING_EFFORT",
        "WINSTON_DEEP_RESEARCH_MAX_TOKENS",
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


def test_winston_can_use_openai_compatible_deepseek_with_thinking_disabled(monkeypatch):
    clear_winston_env(monkeypatch)
    monkeypatch.setenv("WINSTON_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("WINSTON_LLM_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("WINSTON_LLM_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("WINSTON_LLM_API_KEY", "deepseek-key")
    monkeypatch.setenv("WINSTON_LLM_THINKING", "disabled")
    monkeypatch.setenv("WINSTON_LLM_REASONING_EFFORT", "low")
    engine = TradingViewWebhookEngine(winston_config())

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "DeepSeek Winston is online."}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        assert url == "https://api.deepseek.com/v1/chat/completions"
        assert headers["Authorization"] == "Bearer deepseek-key"
        assert json["model"] == "deepseek-v4-flash"
        assert json["thinking"] == {"type": "disabled"}
        assert json["reasoning_effort"] == "low"
        return FakeResponse()

    monkeypatch.setattr("bot.webhook_server.requests.post", fake_post)

    result = engine.winston_reply("status check")

    assert result["provider"] == "openai_compatible"
    assert result["model"] == "deepseek-v4-flash"
    assert result["llm_used"] is True
    assert result["reply"] == "DeepSeek Winston is online."


def test_winston_falls_back_to_ollama_when_primary_cloud_brain_fails(monkeypatch):
    clear_winston_env(monkeypatch)
    monkeypatch.setenv("WINSTON_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("WINSTON_LLM_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("WINSTON_LLM_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("WINSTON_LLM_API_KEY", "deepseek-key")
    monkeypatch.setenv("WINSTON_LLM_FALLBACK_PROVIDER", "ollama")
    monkeypatch.setenv("WINSTON_LLM_FALLBACK_BASE_URL", "http://ollama:11434")
    monkeypatch.setenv("WINSTON_LLM_FALLBACK_MODEL", "qwen3:1.7b")
    monkeypatch.setenv("WINSTON_LLM_FALLBACK_THINK", "false")
    engine = TradingViewWebhookEngine(winston_config())

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": "Local fallback Winston is ready."}}

    def fake_post(url, headers=None, json=None, timeout=None):
        if url.endswith("/chat/completions"):
            raise RuntimeError("deepseek unavailable")
        assert url == "http://ollama:11434/api/chat"
        assert json["model"] == "qwen3:1.7b"
        assert json["think"] is False
        return FakeResponse()

    monkeypatch.setattr("bot.webhook_server.requests.post", fake_post)

    result = engine.winston_reply("status check")

    assert result["provider"] == "ollama"
    assert result["model"] == "qwen3:1.7b"
    assert result["llm_used"] is True
    assert result["degraded"] is True
    assert result["fallback_from"] == "openai_compatible"
    assert result["reply"] == "Local fallback Winston is ready."


def test_winston_research_can_use_openai_compatible_deepseek_pro(monkeypatch):
    clear_winston_env(monkeypatch)
    monkeypatch.setenv("WINSTON_RESEARCH_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("WINSTON_RESEARCH_LLM_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("WINSTON_RESEARCH_LLM_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("WINSTON_RESEARCH_LLM_API_KEY", "research-key")
    monkeypatch.setenv("WINSTON_RESEARCH_THINKING", "enabled")
    monkeypatch.setenv("WINSTON_RESEARCH_REASONING_EFFORT", "high")
    monkeypatch.setenv("WINSTON_RESEARCH_MAX_TOKENS", "900")
    engine = TradingViewWebhookEngine(winston_config())

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "DeepSeek Pro research note ready."}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        assert url == "https://api.deepseek.com/v1/chat/completions"
        assert headers["Authorization"] == "Bearer research-key"
        assert json["model"] == "deepseek-v4-pro"
        assert json["max_tokens"] == 900
        assert json["thinking"] == {"type": "enabled"}
        assert json["reasoning_effort"] == "high"
        return FakeResponse()

    monkeypatch.setattr("bot.webhook_server.requests.post", fake_post)

    result = engine.winston_research("SPY prep")

    assert result["provider"] == "openai_compatible"
    assert result["model"] == "deepseek-v4-pro"
    assert result["research_used"] is True
    assert result["reply"] == "DeepSeek Pro research note ready."


def test_winston_deep_research_uses_dedicated_model_and_budget(monkeypatch):
    clear_winston_env(monkeypatch)
    monkeypatch.setenv("WINSTON_DEEP_RESEARCH_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("WINSTON_DEEP_RESEARCH_LLM_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("WINSTON_DEEP_RESEARCH_LLM_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("WINSTON_DEEP_RESEARCH_LLM_API_KEY", "deep-research-key")
    monkeypatch.setenv("WINSTON_DEEP_RESEARCH_THINKING", "disabled")
    monkeypatch.setenv("WINSTON_DEEP_RESEARCH_MAX_TOKENS", "1500")
    engine = TradingViewWebhookEngine(winston_config())

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "Deep research memo ready."}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        assert url == "https://api.deepseek.com/v1/chat/completions"
        assert headers["Authorization"] == "Bearer deep-research-key"
        assert json["model"] == "deepseek-v4-pro"
        assert json["max_tokens"] == 1500
        assert json["thinking"] == {"type": "disabled"}
        assert "Deep Research Mode" in json["messages"][0]["content"]
        return FakeResponse()

    monkeypatch.setattr("bot.webhook_server.requests.post", fake_post)

    result = engine.winston_deep_research("SPY deep prep")

    assert result["provider"] == "openai_compatible"
    assert result["model"] == "deepseek-v4-pro"
    assert result["mode"] == "deep_research"
    assert result["reply"] == "Deep research memo ready."


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
