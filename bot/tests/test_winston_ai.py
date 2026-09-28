from datetime import datetime, timezone

from bot.core.types import Bar
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
        "WINSTON_TTS_REQUIRED_VOICE",
        "WINSTON_TTS_RESPONSE_FORMAT",
        "FISH_API_KEY",
        "FISH_TTS_VOICE",
        "FISH_TTS_REFERENCE_ID",
        "FISH_TTS_MODEL",
        "FISH_TTS_SPEED",
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
        "APCA_API_KEY_ID",
        "APCA_API_SECRET_KEY",
        "APCA_API_BASE_URL",
        "APCA_API_DATA_URL",
    ):
        monkeypatch.delenv(name, raising=False)


def test_winston_defaults_to_safe_local_rules(monkeypatch):
    clear_winston_env(monkeypatch)
    engine = TradingViewWebhookEngine(winston_config())

    status = engine.winston.status()
    result = engine.winston_reply("give me the risk")

    assert status["brain"]["provider"] == "winston_rule_based_v1"
    assert status["voice"]["provider"] == "pockettts"
    assert status["voice"]["configured"] is False
    assert status["voice"]["voice"] == "winston"
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


def test_winston_live_quote_uses_alpaca_market_data(monkeypatch):
    clear_winston_env(monkeypatch)
    monkeypatch.setenv("APCA_API_KEY_ID", "paper-key")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "paper-secret")
    engine = TradingViewWebhookEngine(winston_config())

    class FakeResponse:
        status_code = 200
        text = "{}"

        def json(self):
            return {"trade": {"p": 543.21, "s": 100, "t": "2026-07-30T14:30:00Z"}}

    def fake_get(url, headers=None, params=None, timeout=None):
        assert url == "https://data.alpaca.markets/v2/stocks/SPY/trades/latest"
        assert headers["APCA-API-KEY-ID"] == "paper-key"
        assert params == {"feed": "iex"}
        return FakeResponse()

    monkeypatch.setattr("bot.webhook_server.requests.get", fake_get)

    result = engine.winston_reply("Leo, what is the live price of SPY ETF?")

    assert result["provider"] == "winston_market_quote_v1"
    assert result["intent"] == "market_quote"
    assert result["llm_used"] is False
    assert result["quote"]["source"] == "alpaca_latest_trade"
    assert result["quote"]["price"] == 543.21
    assert "SPY is trading around $543.21" in result["reply"]


def test_winston_live_quote_falls_back_to_scanner_bar(monkeypatch):
    clear_winston_env(monkeypatch)
    engine = TradingViewWebhookEngine(winston_config())

    def fake_scanner_bars(*, symbol, asset_type):
        assert symbol == "SPY"
        assert asset_type == "equity"
        return [Bar(datetime(2026, 7, 30, 14, 31, tzinfo=timezone.utc), 500, 502, 499, 501.23, 12345)]

    monkeypatch.setattr(engine, "_positions_snapshot", lambda: ([], None))
    monkeypatch.setattr(engine, "_fetch_scanner_bars", fake_scanner_bars)

    result = engine.winston_reply("current quote for spy")

    assert result["provider"] == "winston_market_quote_v1"
    assert result["quote"]["source"] == "scanner_latest_bar"
    assert result["quote"]["price"] == 501.23
    assert "SPY is trading around $501.23" in result["reply"]


def test_winston_routes_safe_enhancement_questions_to_mentor_context_pack(monkeypatch):
    clear_winston_env(monkeypatch)
    engine = TradingViewWebhookEngine(winston_config())
    pack = {
        "version": "winston_mentor_context_pack_v1",
        "loaded": True,
        "tools": [
            {"key": "daily_root_cause", "label": "Daily Root-Cause Brief", "focus": "Strategy drift", "summary": "Daily Root-Cause Brief points first to Strategy drift.", "next_action": "Compare current trade frequency."},
            {"key": "broker_reconciliation", "label": "Broker/Data Reconciliation Score", "score": 94, "summary": "Broker/Data Reconciliation score is 94/100."},
        ],
        "read_only": True,
        "advisory_only": True,
    }
    monkeypatch.setattr(
        engine,
        "mentor_report_payload",
        lambda scope="weekly", days=None, alert_ref="": {
            "ok": True,
            "headline": "Mentor ready",
            "recommendation": {"title": "Review drift", "instruction": "Compare current trade frequency."},
            "metrics": {},
            "sample": {},
            "profile": {},
            "winston_mentor_context_pack": pack,
        },
    )

    result = engine.winston_reply("What is the daily root cause?")

    assert result["intent"] == "velez_mentor"
    assert result["provider"] == "velez_mentor_rules_v1"
    assert result["winston_mentor_context_pack"]["version"] == "winston_mentor_context_pack_v1"
    assert "Strategy drift" in result["reply"]


def test_winston_general_messages_include_compact_mentor_context_pack(monkeypatch):
    clear_winston_env(monkeypatch)
    engine = TradingViewWebhookEngine(winston_config())
    monkeypatch.setattr(
        engine,
        "winston_mentor_context_pack_payload",
        lambda report=None: {
            "ok": True,
            "context_pack": {
                "version": "winston_mentor_context_pack_v1",
                "loaded": True,
                "tools": [{"key": "trade_quality_heatmap", "label": "Trade Quality Heatmap", "closed_trades": 12}],
                "read_only": True,
            },
        },
    )

    messages = engine.winston._messages("Can you read Mentor?")

    assert "compact Mentor Safe Enhancement context pack" in messages[0]["content"]
    assert "mentor_context_pack" in messages[1]["content"]
    assert "Trade Quality Heatmap" in messages[1]["content"]


def test_winston_velez_principles_pack_is_read_only_and_separate_from_mentor(monkeypatch):
    clear_winston_env(monkeypatch)
    engine = TradingViewWebhookEngine(winston_config())

    payload = engine.winston_velez_principles_pack_payload()
    pack = payload["context_pack"]

    assert payload["ok"] is True
    assert pack["version"] == "winston_velez_principles_pack_v1"
    assert pack["read_only"] is True
    assert pack["can_submit_orders"] is False
    assert pack["can_change_guardrails"] is False
    assert "Bull Mentor" in pack["role_boundary"]["bull_mentor"]
    assert any(item["label"] == "Elephant Bar" for item in pack["setup_reference"])
    assert any(item["key"] == "webhook_confluence" for item in pack["execution_gates"])


def test_winston_routes_strategy_questions_to_velez_principles_pack(monkeypatch):
    clear_winston_env(monkeypatch)
    engine = TradingViewWebhookEngine(winston_config())

    result = engine.winston_reply("Do you know all Velez strategies and principles?")

    assert result["intent"] == "velez_principles"
    assert result["provider"] == "winston_velez_principles_v1"
    assert result["llm_used"] is False
    assert result["winston_velez_principles_pack"]["version"] == "winston_velez_principles_pack_v1"
    assert "Bull Mentor still owns coaching" in result["reply"]


def test_winston_keeps_coaching_questions_on_mentor_route(monkeypatch):
    clear_winston_env(monkeypatch)
    engine = TradingViewWebhookEngine(winston_config())
    monkeypatch.setattr(
        engine,
        "mentor_report_payload",
        lambda scope="weekly", days=None, alert_ref="": {
            "ok": True,
            "headline": "Mentor ready",
            "recommendation": {"title": "Review drift", "instruction": "Compare current trade frequency."},
            "metrics": {},
            "sample": {},
            "profile": {},
            "winston_mentor_context_pack": {
                "version": "winston_mentor_context_pack_v1",
                "loaded": True,
                "tools": [{"key": "drill_scheduler", "label": "Mentor Drill Scheduler", "summary": "Daily drill is ready."}],
            },
        },
    )

    result = engine.winston_reply("What daily drill should I run?")

    assert result["intent"] == "velez_mentor"
    assert result["provider"] == "velez_mentor_rules_v1"
    assert "winston_velez_principles_pack" not in result


def test_winston_general_messages_include_velez_principles_pack(monkeypatch):
    clear_winston_env(monkeypatch)
    engine = TradingViewWebhookEngine(winston_config())

    messages = engine.winston._messages("Explain the no chasing rule.")

    assert "Velez Principles Pack" in messages[0]["content"]
    assert "velez_principles_pack" in messages[1]["content"]
    assert "No chasing" in messages[1]["content"]


def test_mentor_voice_briefing_includes_context_pack_and_voice_line(monkeypatch):
    clear_winston_env(monkeypatch)
    engine = TradingViewWebhookEngine(winston_config())
    pack = {
        "version": "winston_mentor_context_pack_v1",
        "loaded": True,
        "tools": [
            {"key": "daily_root_cause", "focus": "Execution drift"},
            {"key": "guardrail_do_not_touch", "rules_flagged": 2},
            {"key": "broker_reconciliation", "score": 97},
            {"key": "drill_scheduler", "recommended": {"title": "Daily drill: Execution drift"}},
        ],
    }
    monkeypatch.setattr(engine, "winston_mentor_context_pack_payload", lambda report=None: {"ok": True, "context_pack": pack})
    monkeypatch.setattr(engine, "daily_brief_payload", lambda: {"lines": ["Wait for structure."], "sections": {}, "pending_approvals": []})
    monkeypatch.setattr(engine, "lifecycle_payload", lambda *args, **kwargs: {"summary": {}, "readback": "Lifecycle idle."})
    monkeypatch.setattr(engine, "risk_status_payload", lambda: {"risk": {"max_dollar_risk_per_trade": 1000}})

    payload = engine.mentor_voice_briefing_payload("morning")

    assert payload["ok"] is True
    assert payload["mentor"]["winston_mentor_context_pack"]["version"] == "winston_mentor_context_pack_v1"
    assert "Mentor context flags Execution drift" in payload["script"]
    assert "Reconciliation score is 97/100" in payload["script"]


def test_winston_weekly_pnl_uses_alpaca_portfolio_history(monkeypatch):
    clear_winston_env(monkeypatch)
    monkeypatch.setenv("APCA_API_KEY_ID", "paper-key")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "paper-secret")
    engine = TradingViewWebhookEngine(winston_config())

    def fake_history(*, period, timeframe):
        assert period == "1W"
        assert timeframe == "1D"
        return {
            "timestamp": [1785340800, 1785513600],
            "equity": [100000.0, 101250.5],
            "profit_loss": [0.0, 1250.5],
            "profit_loss_pct": [0.0, 0.012505],
            "base_value": 100000.0,
        }

    monkeypatch.setattr(engine.broker, "get_portfolio_history_raw", fake_history)

    result = engine.winston_reply("what is my p&l for the week")

    assert result["provider"] == "winston_broker_pnl_v1"
    assert result["intent"] == "weekly_pnl"
    assert result["llm_used"] is False
    assert result["pnl"]["source"] == "alpaca_portfolio_history"
    assert result["pnl"]["week_pl"] == 1250.5
    assert "up $1,250.50 for the trailing week" in result["reply"]


def test_winston_today_close_routes_to_connected_daily_bar(monkeypatch):
    clear_winston_env(monkeypatch)
    engine = TradingViewWebhookEngine(winston_config())

    def fake_close(symbol):
        assert symbol == "SPY"
        return {
            "ok": True,
            "symbol": "SPY",
            "price": 743.27,
            "session_date": "2026-07-30",
            "is_today": True,
            "source": "alpaca_daily_bar",
            "source_label": "Alpaca IEX daily bar",
        }

    monkeypatch.setattr(engine, "market_close_payload", fake_close)

    result = engine.winston_reply("what did spy close at today")

    assert result["provider"] == "winston_market_close_v1"
    assert result["intent"] == "market_close"
    assert result["llm_used"] is False
    assert result["close"]["source"] == "alpaca_daily_bar"
    assert "SPY today's daily close was $743.27" in result["reply"]


def test_market_close_prefers_consolidated_fallback_over_iex(monkeypatch):
    clear_winston_env(monkeypatch)
    engine = TradingViewWebhookEngine(winston_config())

    def fake_alpaca(symbol, *, feed=None):
        assert symbol == "SPY"
        if feed == "sip":
            raise RuntimeError("sip_subscription_unavailable")
        return {"ok": True, "symbol": symbol, "price": 741.63, "source": "alpaca_iex_daily_bar"}

    monkeypatch.setattr(engine, "_alpaca_daily_close", fake_alpaca)
    monkeypatch.setattr(
        engine,
        "_yfinance_daily_close",
        lambda symbol: {"ok": True, "symbol": symbol, "price": 741.69, "source": "yfinance_daily_bar"},
    )

    result = engine.market_close_payload("SPY")

    assert result["source"] == "yfinance_daily_bar"
    assert result["price"] == 741.69
    assert result["sources_checked"][0]["source"] == "alpaca_sip_daily_bar"
    assert result["sources_checked"][0]["ok"] is False


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
    monkeypatch.setenv("WINSTON_LLM_MODEL", "qwen3:8b")
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
        assert json["model"] == "qwen3:8b"
        assert json["think"] is False
        return FakeResponse()

    monkeypatch.setattr("bot.webhook_server.requests.post", fake_post)

    result = engine.winston_reply("status check")

    assert result["provider"] == "ollama"
    assert result["model"] == "qwen3:8b"
    assert result["reply"] == "Winston is online with guarded voice execution."


def test_winston_can_use_openai_compatible_groq_with_extra_body(monkeypatch):
    clear_winston_env(monkeypatch)
    monkeypatch.setenv("WINSTON_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("WINSTON_LLM_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("WINSTON_LLM_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setenv("WINSTON_LLM_API_KEY", "groq-key")
    monkeypatch.setenv("WINSTON_LLM_EXTRA_BODY_JSON", '{"reasoning_format":"hidden"}')
    engine = TradingViewWebhookEngine(winston_config())

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "Groq Winston is online."}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        assert url == "https://api.groq.com/openai/v1/chat/completions"
        assert headers["Authorization"] == "Bearer groq-key"
        assert json["model"] == "openai/gpt-oss-20b"
        assert json["reasoning_format"] == "hidden"
        assert json["reasoning_effort"] == "low"
        return FakeResponse()

    monkeypatch.setattr("bot.webhook_server.requests.post", fake_post)

    result = engine.winston_reply("status check")

    assert result["provider"] == "openai_compatible"
    assert result["model"] == "openai/gpt-oss-20b"
    assert result["llm_used"] is True
    assert result["reply"] == "Groq Winston is online."


def test_winston_falls_back_to_ollama_when_primary_cloud_brain_fails(monkeypatch):
    clear_winston_env(monkeypatch)
    monkeypatch.setenv("WINSTON_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("WINSTON_LLM_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("WINSTON_LLM_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setenv("WINSTON_LLM_API_KEY", "groq-key")
    monkeypatch.setenv("WINSTON_LLM_FALLBACK_PROVIDER", "ollama")
    monkeypatch.setenv("WINSTON_LLM_FALLBACK_BASE_URL", "http://ollama:11434")
    monkeypatch.setenv("WINSTON_LLM_FALLBACK_MODEL", "qwen3:4b")
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
            raise RuntimeError("groq unavailable")
        assert url == "http://ollama:11434/api/chat"
        assert json["model"] == "qwen3:4b"
        assert json["think"] is False
        return FakeResponse()

    monkeypatch.setattr("bot.webhook_server.requests.post", fake_post)

    result = engine.winston_reply("status check")

    assert result["provider"] == "ollama"
    assert result["model"] == "qwen3:4b"
    assert result["llm_used"] is True
    assert result["degraded"] is True
    assert result["fallback_from"] == "openai_compatible"
    assert result["reply"] == "Local fallback Winston is ready."


def test_winston_research_can_use_openai_compatible_groq_qwen(monkeypatch):
    clear_winston_env(monkeypatch)
    monkeypatch.setenv("WINSTON_RESEARCH_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("WINSTON_RESEARCH_LLM_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("WINSTON_RESEARCH_LLM_MODEL", "qwen/qwen3.6-27b")
    monkeypatch.setenv("WINSTON_RESEARCH_LLM_API_KEY", "research-key")
    monkeypatch.setenv("WINSTON_RESEARCH_LLM_EXTRA_BODY_JSON", '{"reasoning_format":"hidden"}')
    monkeypatch.setenv("WINSTON_RESEARCH_MAX_TOKENS", "900")
    engine = TradingViewWebhookEngine(winston_config())

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "Groq Qwen research note ready."}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        assert url == "https://api.groq.com/openai/v1/chat/completions"
        assert headers["Authorization"] == "Bearer research-key"
        assert json["model"] == "qwen/qwen3.6-27b"
        assert json["max_tokens"] == 900
        assert json["reasoning_format"] == "hidden"
        return FakeResponse()

    monkeypatch.setattr("bot.webhook_server.requests.post", fake_post)

    result = engine.winston_research("SPY prep")

    assert result["provider"] == "openai_compatible"
    assert result["model"] == "qwen/qwen3.6-27b"
    assert result["research_used"] is True
    assert result["reply"] == "Groq Qwen research note ready."


def test_winston_deep_research_uses_dedicated_model_and_budget(monkeypatch):
    clear_winston_env(monkeypatch)
    monkeypatch.setenv("WINSTON_DEEP_RESEARCH_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("WINSTON_DEEP_RESEARCH_LLM_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("WINSTON_DEEP_RESEARCH_LLM_MODEL", "qwen/qwen3.6-27b")
    monkeypatch.setenv("WINSTON_DEEP_RESEARCH_LLM_API_KEY", "deep-research-key")
    monkeypatch.setenv("WINSTON_DEEP_RESEARCH_LLM_EXTRA_BODY_JSON", '{"reasoning_format":"hidden"}')
    monkeypatch.setenv("WINSTON_DEEP_RESEARCH_MAX_TOKENS", "1500")
    engine = TradingViewWebhookEngine(winston_config())

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "Deep research memo ready."}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        assert url == "https://api.groq.com/openai/v1/chat/completions"
        assert headers["Authorization"] == "Bearer deep-research-key"
        assert json["model"] == "qwen/qwen3.6-27b"
        assert json["max_tokens"] == 1500
        assert json["reasoning_format"] == "hidden"
        assert "Deep Research Mode" in json["messages"][0]["content"]
        return FakeResponse()

    monkeypatch.setattr("bot.webhook_server.requests.post", fake_post)

    result = engine.winston_deep_research("SPY deep prep")

    assert result["provider"] == "openai_compatible"
    assert result["model"] == "qwen/qwen3.6-27b"
    assert result["mode"] == "deep_research"
    assert result["reply"] == "Deep research memo ready."


def test_winston_pockettts_speech_uses_openai_compatible_endpoint(monkeypatch):
    clear_winston_env(monkeypatch)
    monkeypatch.setenv("WINSTON_TTS_PROVIDER", "pockettts")
    monkeypatch.setenv("WINSTON_TTS_BASE_URL", "http://127.0.0.1:8018/v1")
    monkeypatch.setenv("WINSTON_TTS_API_KEY", "test-key")
    monkeypatch.setenv("WINSTON_TTS_VOICE", "winston")
    engine = TradingViewWebhookEngine(winston_config())

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "audio/mpeg"}
        content = b"fake-mp3"
        text = ""

    def fake_post(url, headers=None, json=None, timeout=None):
        assert url == "http://127.0.0.1:8018/v1/audio/speech"
        assert headers["Authorization"] == "Bearer test-key"
        assert json["voice"] == "winston"
        assert json["response_format"] == "mp3"
        return FakeResponse()

    monkeypatch.setattr("bot.webhook_server.requests.post", fake_post)

    result = engine.winston.synthesize_speech("hello from Winston")

    assert result["ok"] is True
    assert result["media_type"] == "audio/mpeg"
    assert result["content"] == b"fake-mp3"
    assert result["voice"] == "winston"
    assert result["latency_ms"] >= 0


def test_winston_fish_speech_uses_winston_reference(monkeypatch):
    clear_winston_env(monkeypatch)
    monkeypatch.setenv("WINSTON_TTS_PROVIDER", "fish")
    monkeypatch.setenv("FISH_API_KEY", "fish-key")
    monkeypatch.setenv("WINSTON_TTS_VOICE", "winston")
    engine = TradingViewWebhookEngine(winston_config())

    def fake_convert(text, *, api_key, reference_id, model, fmt, speed):
        assert text == "hello from Winston"
        assert api_key == "fish-key"
        assert reference_id == "3755d07d7b474b2bb7260ad75789b9a8"
        assert model == "s2-pro"
        assert fmt == "mp3"
        assert speed == 1.0
        return b"fish-mp3"

    monkeypatch.setattr(engine.winston, "_fish_tts_convert", fake_convert)

    result = engine.winston.synthesize_speech("hello from Winston")

    assert result["ok"] is True
    assert result["provider"] == "fish"
    assert result["voice"] == "winston"
    assert result["model"] == "s2-pro"
    assert result["content"] == b"fish-mp3"


def test_winston_speech_rejects_non_winston_voice(monkeypatch):
    clear_winston_env(monkeypatch)
    monkeypatch.setenv("WINSTON_TTS_PROVIDER", "fish")
    monkeypatch.setenv("FISH_API_KEY", "fish-key")
    monkeypatch.setenv("WINSTON_TTS_VOICE", "jarvis")
    engine = TradingViewWebhookEngine(winston_config())

    result = engine.winston.synthesize_speech("hello from Winston")

    assert result["ok"] is False
    assert result["reason"] == "tts_voice_lock_mismatch"
    assert result["required_voice"] == "winston"
    assert result["voice"] == "jarvis"


def test_winston_speech_rejects_browser_voice_fallback(monkeypatch):
    clear_winston_env(monkeypatch)
    monkeypatch.setenv("WINSTON_TTS_PROVIDER", "browser")
    engine = TradingViewWebhookEngine(winston_config())

    result = engine.winston.synthesize_speech("hello from Winston")

    assert result["ok"] is False
    assert result["reason"] == "server_tts_not_configured"
    assert result["provider"] == "browser"
    assert result["required_voice"] == "winston"
