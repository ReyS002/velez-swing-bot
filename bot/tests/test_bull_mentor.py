from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from bot.core.bull_mentor import BullMentorEngine
from bot.core.risk import RiskManager
from bot.core.types import Bar
from bot.journal_store import JournalStore
from bot.webhook_server import TradingViewWebhookEngine, create_app


NOW = datetime(2026, 7, 30, 16, 0, tzinfo=timezone.utc)


def mentor_config(*, equity=100_000, prop=False):
    return {
        "timezone": "America/New_York",
        "portfolio": {"initial_cash": equity},
        "bull_mentor": {
            "enabled": True,
            "weekly_days": 7,
            "minimum_performance_sample": 5,
            "slippage_warning_bps": 10,
        },
        "risk": {
            "risk_per_trade": 0.005,
            "max_dollar_risk_per_trade": 1000,
            "max_daily_loss_pct": 0.02,
            "max_consecutive_losses": 3,
            "max_open_positions": 50,
            "max_leverage": 2,
            "max_order_qty": 100000,
            "max_stop_pct": 0.1,
            "matrix": {
                "enabled": True,
                "institutional_threshold": 1_000_000,
                "max_participation_rate": 0.05,
            },
            "prop_firm_shield": {
                "enabled": prop,
                "risk_per_trade_pct": 0.6,
                "max_daily_loss_pct": 1.5,
                "max_open_positions": 2,
                "max_risk_increase_pct": 10,
            },
        },
        "webhook": {
            "auth_required": False,
            "execute_orders": False,
            "paper_only": True,
        },
        "symbols": [{"symbol": "SPY", "contract_multiplier": 1}],
        "bullpilot_strategy": {},
    }


def snapshot(
    ref,
    *,
    timestamp="2026-07-30T14:00:00+00:00",
    symbol="SPY",
    location="location_3_near_200_sma",
    qty=100,
    entry=100,
    stop=99,
    max_risk=100,
    score=95,
    execution_plan=None,
):
    return {
        "timestamp": timestamp,
        "alert_ref": ref,
        "status": "proposed",
        "reason": "execution_disabled",
        "symbol": symbol,
        "side": "buy",
        "play": "elephant_bar",
        "qty": qty,
        "entry_price": entry,
        "stop_price": stop,
        "location": location,
        "max_dollar_risk": max_risk,
        "execution_plan": execution_plan,
        "confidence_receipt": {
            "score": score,
            "grade": "A" if score >= 85 else "C",
            "checks": [
                {"name": "No chase flag", "ok": True},
                {"name": "Location qualified", "ok": bool(location)},
            ],
        },
    }


def build_mentor(tmp_path, config=None):
    cfg = config or mentor_config()
    journal = JournalStore(cfg, db_path=str(tmp_path / "mentor.sqlite3"))
    risk = RiskManager(cfg["risk"])
    return journal, risk, BullMentorEngine(cfg, journal, risk)


def test_mentor_builds_evidence_backed_scores_and_withholds_thin_expectancy(tmp_path):
    journal, _, mentor = build_mentor(tmp_path)
    journal.record_decision(snapshot("good-1"))
    journal.record_decision(snapshot("missing-location", location=None, score=60))
    journal.record_trade_outcome(
        {
            "timestamp": "2026-07-30T15:30:00+00:00",
            "alert_ref": "good-1",
            "symbol": "SPY",
            "status": "closed",
            "terminal": True,
            "r_multiple": 1.5,
            "pnl": 150,
            "setup": "elephant_bar",
        }
    )

    report = mentor.report(scope="weekly", now=NOW, persist=True)

    assert report["ok"] is True
    assert report["advisory_only"] is True
    assert report["guardrails"]["can_submit_orders"] is False
    assert report["metrics"]["discipline"]["location_rate"] == 50.0
    assert report["metrics"]["performance"]["terminal_trades"] == 1
    assert report["metrics"]["performance"]["sufficient_sample"] is False
    performance_score = next(item for item in report["scorecards"] if item["key"] == "performance_quality")
    assert performance_score["score"] is None
    assert any(item["alert_ref"] == "missing-location" for item in report["evidence"])
    assert report["drill"]["status"] == "active"
    assert report["report_id"] > 0


def test_mentor_reveals_expectancy_only_after_minimum_terminal_sample(tmp_path):
    journal, _, mentor = build_mentor(tmp_path)
    r_values = [1.5, -1.0, 2.0, -0.5, 1.0]
    for index, r_value in enumerate(r_values):
        ref = f"trade-{index}"
        journal.record_decision(snapshot(ref))
        journal.record_trade_outcome(
            {
                "timestamp": f"2026-07-{24 + index:02d}T15:30:00+00:00",
                "alert_ref": ref,
                "symbol": "SPY",
                "status": "closed",
                "terminal": True,
                "r_multiple": r_value,
                "pnl": r_value * 100,
                "setup": "elephant_bar",
            }
        )

    report = mentor.report(scope="weekly", days=10, now=NOW)
    performance = report["metrics"]["performance"]

    assert performance["sufficient_sample"] is True
    assert performance["terminal_trades"] == 5
    assert performance["win_rate"] == 60.0
    assert performance["expectancy_r"] == 0.6
    assert next(item for item in report["scorecards"] if item["key"] == "performance_quality")["score"] == 65


def test_institutional_mentor_audits_participation_and_slippage(tmp_path):
    cfg = mentor_config(equity=5_000_000)
    journal, _, mentor = build_mentor(tmp_path, cfg)
    plan = {
        "algorithm": "vwap",
        "requested_qty": 120,
        "executable_qty": 100,
        "participation_rate": 0.05,
        "liquidity_limited": True,
        "slices": [
            {"sequence": 1, "qty": 60, "participation_cap_qty": 50},
            {"sequence": 2, "qty": 40, "participation_cap_qty": 50},
        ],
    }
    decision = snapshot("inst-1", qty=100, execution_plan=plan)
    journal.record_decision(
        decision,
        order_payload={"_bullpilot_execution_plan": plan},
        broker_response={"filled_avg_price": "100.20"},
    )

    report = mentor.report(scope="today", now=NOW)
    execution = report["metrics"]["execution"]

    assert report["mode"] == "institutional"
    assert execution["planned_parents"] == 1
    assert execution["planned_fill_ratio"] == 83.3
    assert execution["participation_breaches"] == 1
    assert execution["average_slippage_bps"] == 20.0
    assert any(item["key"] == "participation_breach" for item in report["patterns"])


def test_prop_mentor_detects_risk_size_escalation(tmp_path):
    cfg = mentor_config(prop=True)
    journal, risk, mentor = build_mentor(tmp_path, cfg)
    journal.record_decision(snapshot("prop-1", timestamp="2026-07-30T14:00:00+00:00", qty=100, max_risk=100))
    journal.record_decision(snapshot("prop-2", timestamp="2026-07-30T15:00:00+00:00", qty=150, max_risk=150))

    report = mentor.report(scope="today", now=NOW)

    assert report["mode"] == "prop"
    assert report["metrics"]["prop"]["largest_risk_increase_pct"] == 50.0
    assert any(item["key"] == "risk_size_escalation" for item in report["patterns"])
    assert report["recommendation"]["dimension"] == "risk_discipline"


def test_mentor_profile_and_drill_memory_are_persistent(tmp_path):
    journal, _, mentor = build_mentor(tmp_path)
    journal.record_decision(snapshot("memory-1"))
    report = mentor.report(scope="today", now=NOW)
    drill_id = report["drill"]["id"]

    profile = mentor.update_profile(
        {
            "experience_level": "advanced",
            "primary_mode": "institutional",
            "coaching_style": "socratic",
            "goals": ["Keep execution slippage below 8 bps"],
            "focus_areas": ["execution_quality"],
        }
    )
    completed = mentor.set_drill_status(drill_id, "completed")

    reloaded = BullMentorEngine(mentor_config(), journal, None)
    assert profile["local_only"] is True
    assert reloaded.profile()["goals"] == ["Keep execution slippage below 8 bps"]
    assert completed["drill"]["status"] == "completed"
    assert journal.mentor_drills(include_completed=False) == []


def test_mode_switch_and_trade_review_do_not_duplicate_active_drills(tmp_path):
    journal, _, mentor = build_mentor(tmp_path)
    journal.record_decision(snapshot("drill-dedupe"))
    first = mentor.report(scope="weekly", now=NOW)

    mentor.update_profile({"primary_mode": "institutional"})
    second = mentor.report(scope="weekly", now=NOW)
    trade = mentor.report(scope="trade", alert_ref="drill-dedupe", now=NOW)

    assert first["drill"]["id"] == second["drill"]["id"]
    assert len(journal.mentor_drills(include_completed=False)) == 1
    assert trade["drill"]["status"] == "preview"
    assert trade["drill"]["id"] is None
    assert len(journal.mentor_drills(include_completed=False)) == 1


def test_mentor_rule_answer_refuses_trade_action(tmp_path):
    journal, _, mentor = build_mentor(tmp_path)
    journal.record_decision(snapshot("safe-1"))
    report = mentor.report(scope="today", now=NOW)

    answer = mentor.rule_answer("Buy SPY and approve the order", report)

    assert "advisory only" in answer
    assert "cannot place, approve" in answer


def test_mentor_api_is_end_to_end_and_profile_updates_recompute_mode(monkeypatch):
    cfg = mentor_config()
    app = create_app(cfg)
    engine = app.state.engine
    engine.journal.record_decision(snapshot("api-mentor"))
    client = TestClient(app)

    today = client.get("/api/mentor/today")
    profile = client.post(
        "/api/mentor/profile",
        json={
            "experience_level": "developing",
            "primary_mode": "institutional",
            "coaching_style": "concise",
            "goals": ["Audit every child-order schedule"],
        },
    )
    question = client.post("/api/mentor/ask", json={"question": "What should I improve?", "scope": "today"})

    assert today.status_code == 200
    assert today.json()["version"] == "bull_mentor_v1"
    assert profile.status_code == 200
    assert profile.json()["report"]["mode"] == "institutional"
    assert question.status_code == 200
    assert question.json()["provider"] == "velez_mentor_rules_v1"
    assert question.json()["report"]["guardrails"]["can_change_risk"] is False


def test_mentor_can_be_disabled_without_affecting_daily_review():
    cfg = mentor_config()
    cfg["bull_mentor"]["enabled"] = False
    app = create_app(cfg)
    client = TestClient(app)

    mentor = client.get("/api/mentor/today")
    review = client.get("/api/review/daily")

    assert mentor.json() == {"ok": False, "enabled": False, "reason": "velez_mentor_disabled"}
    assert review.status_code == 200
    assert review.json()["mentor"]["reason"] == "velez_mentor_disabled"


def test_winston_routes_explicit_coaching_request_to_bull_mentor(monkeypatch):
    engine = TradingViewWebhookEngine(mentor_config())
    engine.journal.record_decision(snapshot("winston-mentor"))

    result = engine.winston_reply("Velez Mentor, coach me on my scorecard")

    assert result["intent"] == "velez_mentor"
    assert result["provider"] == "velez_mentor_rules_v1"
    assert result["report"]["advisory_only"] is True


def test_mentor_llm_narrates_bounded_evidence_with_hard_guardrails(monkeypatch):
    monkeypatch.setenv("WINSTON_MENTOR_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("WINSTON_MENTOR_LLM_BASE_URL", "http://mentor-ollama:11434")
    monkeypatch.setenv("WINSTON_MENTOR_LLM_MODEL", "mentor-local:latest")
    monkeypatch.setenv("WINSTON_MENTOR_THINK", "false")
    engine = TradingViewWebhookEngine(mentor_config())
    current_timestamp = datetime.now(timezone.utc).isoformat()
    engine.journal.record_decision(snapshot("mentor-evidence", timestamp=current_timestamp))

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": "Risk discipline is supported by alert_ref mentor-evidence. Keep the five-trade rehearsal."}}

    def fake_post(url, json=None, timeout=None, headers=None):
        assert url == "http://mentor-ollama:11434/api/chat"
        assert json["model"] == "mentor-local:latest"
        assert json["think"] is False
        assert "Never place, approve, cancel" in json["messages"][0]["content"]
        assert "mentor-evidence" in json["messages"][1]["content"]
        return FakeResponse()

    monkeypatch.setattr("bot.webhook_server.requests.post", fake_post)

    result = engine.mentor_ask({"question": "What should I improve?", "scope": "today"})

    assert result["provider"] == "ollama"
    assert result["llm_used"] is True
    assert "mentor-evidence" in result["reply"]


def test_trade_action_question_never_reaches_mentor_llm(monkeypatch):
    monkeypatch.setenv("WINSTON_MENTOR_LLM_PROVIDER", "ollama")
    engine = TradingViewWebhookEngine(mentor_config())
    engine.journal.record_decision(snapshot("mentor-safe"))

    def forbidden_post(*args, **kwargs):
        raise AssertionError("trade-action mentor question must not reach an LLM")

    monkeypatch.setattr("bot.webhook_server.requests.post", forbidden_post)

    result = engine.mentor_ask({"question": "Buy SPY and approve the order", "scope": "today"})

    assert result["provider"] == "velez_mentor_rules_v1"
    assert result["llm_used"] is False
    assert "advisory only" in result["reply"]


def test_mentor_report_exposes_all_edge_upgrades():
    engine = TradingViewWebhookEngine(mentor_config())
    timestamp = datetime.now(timezone.utc).isoformat()
    engine.journal.record_decision(snapshot("edge-good", timestamp=timestamp))
    engine.journal.record_decision(snapshot("edge-missing-location", timestamp=timestamp, location=None, score=58))
    engine.journal.record_decision(
        {
            **snapshot("edge-shadow", timestamp=timestamp),
            "status": "rejected",
            "reason": "weak_location_discipline",
        }
    )

    report = engine.mentor.report(scope="weekly", persist=True)

    assert set(report["mentor_edges"]) == {
        "response_governor",
        "trade_replay_coach",
        "mistake_fingerprint",
        "shadow_book",
        "pre_trade_challenge",
        "institutional_mode",
        "one_tap_drill_builder",
        "personality_dial",
    }
    assert report["mentor_edges"]["response_governor"]["word_cap"] <= 90
    assert report["mistake_fingerprint"]["dominant"]["key"] != ""
    assert report["shadow_book"]["blocked_count"] >= 1
    assert report["pre_trade_challenge"]["advisory_only"] is True


def test_mentor_response_governor_trims_chatty_llm(monkeypatch):
    monkeypatch.setenv("WINSTON_MENTOR_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("WINSTON_MENTOR_LLM_BASE_URL", "http://mentor-ollama:11434")
    monkeypatch.setenv("WINSTON_MENTOR_LLM_MODEL", "mentor-local:latest")
    engine = TradingViewWebhookEngine(mentor_config())
    engine.journal.record_decision(snapshot("mentor-chatty"))
    chatty = "Based on your current Velez journal data, " + " ".join(f"word{i}" for i in range(180))

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": chatty}}

    monkeypatch.setattr("bot.webhook_server.requests.post", lambda *args, **kwargs: FakeResponse())

    result = engine.mentor_ask({"question": "What should I improve? Keep it short.", "scope": "weekly"})

    assert result["llm_used"] is True
    assert result["response_word_count"] <= result["response_governor"]["word_cap"]
    assert result["response_trimmed"] is True
    assert "Based on your current" not in result["reply"]


def test_one_tap_drill_builder_endpoint_creates_active_drill():
    app = create_app(mentor_config())
    engine = app.state.engine
    engine.journal.record_decision(snapshot("build-drill"))
    client = TestClient(app)

    response = client.post("/api/mentor/drills/build", json={"scope": "weekly"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["drill"]["status"] == "active"
    assert payload["active_drills"]


def test_mentor_chart_observe_scans_tradingview_symbol_without_trade_authority(monkeypatch):
    engine = TradingViewWebhookEngine(mentor_config())
    now = datetime.now(timezone.utc)
    bars = [
        Bar(timestamp=now, open=100 + idx * 0.1, high=101 + idx * 0.1, low=99 + idx * 0.1, close=100.5 + idx * 0.1, volume=1000)
        for idx in range(80)
    ]
    monkeypatch.setattr(
        engine,
        "_fetch_mentor_chart_bars_with_source",
        lambda **kwargs: (bars, "test_bars", [{"source": "test_bars", "ok": True, "rows": len(bars)}]),
    )
    monkeypatch.setattr(engine, "market_quote_payload", lambda symbol: {"ok": True, "symbol": symbol, "price": 108.4, "asof": now})
    monkeypatch.setattr(engine, "_positions_snapshot", lambda: ([], None))

    result = engine.mentor_chart_observe(
        {
            "question": "What setup is visible on this TradingView chart?",
            "symbol": "AMEX:SPY",
            "timeframe": "5",
            "screenshot": "data:image/png;base64,AAAA",
        }
    )

    assert result["ok"] is True
    assert result["intent"] == "velez_mentor_chart_observation"
    assert result["chart_observation"]["symbol"] == "SPY"
    assert result["chart_observation"]["bars_loaded"] == 80
    assert result["chart_observation"]["screenshot"]["provided"] is True
    assert result["report"]["guardrails"]["can_submit_orders"] is False


def test_mentor_chart_observe_accepts_strategy_signal_reason_without_play(monkeypatch):
    engine = TradingViewWebhookEngine(mentor_config())
    now = datetime.now(timezone.utc)
    bars = [
        Bar(timestamp=now, open=100, high=101, low=99, close=100.5, volume=1000)
        for _ in range(3)
    ]

    class FakeScanner:
        def __init__(self, *args, **kwargs):
            return None

        def on_bar(self, symbol, bar):
            return [
                SimpleNamespace(
                    symbol=symbol,
                    side="buy",
                    reason="elephant_bar",
                    metadata={"entry_price": bar.close, "stop_price": bar.low},
                )
            ]

    monkeypatch.setattr("bot.webhook_server.VelezInstitutionalStrategy", FakeScanner)

    scan = engine._mentor_setup_scan("SPY", bars)

    assert scan["signals_found"] == 3
    assert scan["latest_signal"]["play"] == "elephant_bar"
    assert scan["latest_signal"]["entry_price"] == bars[-1].close


def test_mentor_chart_bars_use_tradier_after_empty_alpaca(monkeypatch):
    engine = TradingViewWebhookEngine(mentor_config(), broker=object())
    now = datetime.now(timezone.utc)

    monkeypatch.setattr(engine, "_alpaca_data_request", lambda *args, **kwargs: {"bars": {"SPY": []}})
    monkeypatch.setattr(
        engine,
        "_fetch_mentor_tradier_bars",
        lambda **kwargs: [Bar(timestamp=now, open=100, high=101, low=99, close=100.5, volume=1000)],
    )
    monkeypatch.setattr(engine, "_fetch_mentor_yfinance_bars", lambda **kwargs: [])

    bars, source, attempts = engine._fetch_mentor_chart_bars_with_source(symbol="SPY", timeframe="5Min", asset_type="equity")

    assert len(bars) == 1
    assert source == "tradier_bars"
    assert [item["source"] for item in attempts] == ["alpaca_stock_bars", "tradier_bars"]


def test_mentor_chart_bars_fall_back_to_yfinance_after_alpaca_and_tradier(monkeypatch):
    engine = TradingViewWebhookEngine(mentor_config(), broker=object())
    now = datetime.now(timezone.utc)

    def alpaca_raises(*args, **kwargs):
        raise RuntimeError("alpaca unavailable")

    monkeypatch.setattr(engine, "_alpaca_data_request", alpaca_raises)
    monkeypatch.setattr(engine, "_fetch_mentor_tradier_bars", lambda **kwargs: [])
    monkeypatch.setattr(
        engine,
        "_fetch_mentor_yfinance_bars",
        lambda **kwargs: [Bar(timestamp=now, open=101, high=102, low=100, close=101.5, volume=2000)],
    )

    bars, source, attempts = engine._fetch_mentor_chart_bars_with_source(symbol="SPY", timeframe="5Min", asset_type="equity")

    assert len(bars) == 1
    assert source == "yfinance_bars"
    assert [item["source"] for item in attempts] == ["alpaca_stock_bars", "tradier_bars", "yfinance_bars"]
    assert attempts[0]["ok"] is False


def test_tradier_timesales_rows_convert_to_bars(monkeypatch):
    engine = TradingViewWebhookEngine(mentor_config(), broker=object())
    monkeypatch.setenv("TRADIER_ACCESS_TOKEN", "test-token")

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "series": {
                    "data": [
                        {"time": "2026-08-01T14:30:00Z", "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1234}
                    ]
                }
            }

    def fake_get(url, headers=None, params=None, timeout=None):
        assert url.endswith("/markets/timesales")
        assert headers["Authorization"] == "Bearer test-token"
        assert params["interval"] == "5min"
        return FakeResponse()

    monkeypatch.setattr("bot.webhook_server.requests.get", fake_get)

    bars = engine._fetch_mentor_tradier_bars(symbol="SPY", timeframe="5Min", limit=260)

    assert len(bars) == 1
    assert bars[0].close == 100.5


def test_mentor_chart_observation_includes_source_health_confidence_watch_and_vision_status(monkeypatch):
    engine = TradingViewWebhookEngine(mentor_config())
    now = datetime.now(timezone.utc)
    bars = [
        Bar(timestamp=now, open=100 + idx * 0.1, high=101 + idx * 0.1, low=99 + idx * 0.1, close=100.5 + idx * 0.1, volume=1000)
        for idx in range(140)
    ]
    monkeypatch.setattr(
        engine,
        "_fetch_mentor_chart_bars_with_source",
        lambda **kwargs: (bars, "tradier_bars", [{"source": "alpaca_stock_bars", "ok": False, "rows": 0}, {"source": "tradier_bars", "ok": True, "rows": len(bars)}]),
    )
    monkeypatch.setattr(engine, "market_quote_payload", lambda symbol: {"ok": True, "symbol": symbol, "price": 114.2})
    monkeypatch.setattr(engine, "_positions_snapshot", lambda: ([], None))

    result = engine.mentor_chart_observe({"symbol": "SPY", "screenshot": "data:image/png;base64,AAAA"})
    observation = result["chart_observation"]

    assert observation["source_health"]["active_source"] == "tradier_bars"
    assert observation["confidence_meter"]["score"] >= 70
    assert observation["setup_watch"]["state"] in {"watching_no_setup", "qualified_setup_detected"}
    assert observation["vision"]["pixel_vision_used"] is False
    assert observation["vision"]["status"] == "disabled"


def test_mentor_chart_source_health_endpoint_reports_fallback_order(monkeypatch):
    app = create_app(mentor_config())
    engine = app.state.engine
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(
        engine,
        "_fetch_mentor_chart_bars_with_source",
        lambda **kwargs: ([Bar(timestamp=now, open=100, high=101, low=99, close=100.5, volume=1000)], "yfinance_bars", [{"source": "alpaca_stock_bars", "ok": False, "reason": "empty"}, {"source": "tradier_bars", "ok": False, "rows": 0}, {"source": "yfinance_bars", "ok": True, "rows": 1}]),
    )
    client = TestClient(app)

    response = client.get("/api/mentor/chart/source-health?symbol=SPY&timeframe=5Min")

    assert response.status_code == 200
    payload = response.json()
    assert payload["health"]["active_source"] == "yfinance_bars"
    assert [item["source"] for item in payload["health"]["source_order"]] == ["alpaca_stock_bars", "tradier_bars", "yfinance_bars"]


def test_mentor_no_trade_coach_summarizes_blocked_decisions(tmp_path):
    cfg = mentor_config()
    journal = JournalStore(cfg, db_path=str(tmp_path / "notrade.sqlite3"))
    risk = RiskManager(cfg["risk"])
    mentor = BullMentorEngine(cfg, journal, risk)
    engine = TradingViewWebhookEngine(cfg)
    engine.journal = journal
    engine.mentor = mentor
    engine.mentor_enabled = True
    journal.record_decision({**snapshot("blocked-1"), "status": "rejected", "reason": "risk_daily_loss_guardrail"})

    payload = engine.mentor_no_trade_payload()

    assert payload["coach"]["blocked_count"] == 1
    assert payload["coach"]["top_reason"] == "risk_daily_loss_guardrail"
    assert "prove why" in payload["coach"]["question"]


def test_mentor_setup_watch_endpoint_is_advisory_and_reads_chart(monkeypatch):
    app = create_app(mentor_config())
    engine = app.state.engine
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(
        engine,
        "_fetch_mentor_chart_bars_with_source",
        lambda **kwargs: ([Bar(timestamp=now, open=100, high=101, low=99, close=100.5, volume=1000) for _ in range(80)], "test_bars", [{"source": "test_bars", "ok": True, "rows": 80}]),
    )
    monkeypatch.setattr(engine, "market_quote_payload", lambda symbol: {"ok": True, "symbol": symbol, "price": 100.5})
    monkeypatch.setattr(engine, "_positions_snapshot", lambda: ([], None))
    client = TestClient(app)

    response = client.post("/api/mentor/setup-watch", json={"symbol": "SPY", "timeframe": "5Min"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["advisory_only"] is True
    assert payload["watch"]["state"] in {"watching_no_setup", "qualified_setup_detected"}
    assert payload["chart_observation"]["confidence_meter"]["level"] in {"medium", "high"}


def test_mentor_tradier_diagnostics_masks_missing_token(monkeypatch):
    engine = TradingViewWebhookEngine(mentor_config(), broker=object())
    monkeypatch.delenv("TRADIER_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("TRADIER_API_TOKEN", raising=False)
    monkeypatch.delenv("TRADIER_TOKEN", raising=False)

    payload = engine.mentor_tradier_diagnostics_payload(symbol="SPY", timeframe="5Min")

    assert payload["ok"] is True
    assert payload["secret_masked"] is True
    assert payload["token_present"] is False
    assert "TRADIER_ACCESS_TOKEN" not in str(payload)


def test_mentor_autopsy_backfill_creates_missing_autopsy(tmp_path, monkeypatch):
    cfg = mentor_config()
    cfg["post_trade_autopsy"] = {"enabled": True, "timeframe": "5Min"}
    journal = JournalStore(cfg, db_path=str(tmp_path / "backfill.sqlite3"))
    risk = RiskManager(cfg["risk"])
    mentor = BullMentorEngine(cfg, journal, risk)
    engine = TradingViewWebhookEngine(cfg)
    engine.journal = journal
    engine.mentor = mentor
    engine.mentor_enabled = True
    journal.record_decision(snapshot("closed-1", entry=100, stop=99, qty=100))
    journal.record_trade_outcome(
        {
            "timestamp": "2026-07-30T15:30:00+00:00",
            "alert_ref": "closed-1",
            "symbol": "SPY",
            "status": "closed",
            "terminal": True,
            "r_multiple": -1.0,
            "pnl": -100,
            "exit_price": 99,
            "event_key": "closed-1:SPY:closed:test",
        }
    )
    bars = [
        {"timestamp": f"2026-07-30T14:{str(idx).zfill(2)}:00+00:00", "open": 100, "high": 101, "low": 99, "close": 100.2, "volume": 1000}
        for idx in range(10)
    ]
    monkeypatch.setattr(engine, "_fetch_autopsy_bars", lambda decision: bars)

    payload = engine.mentor_autopsy_backfill_payload(limit=20)

    assert payload["ok"] is True
    assert payload["created"] == 1
    assert payload["autopsies"][0]["backfilled"] is True
    assert journal.trade_autopsy_by_event_key("closed-1:SPY:closed:test") is not None


def build_webhook_engine_with_journal(tmp_path, config=None):
    cfg = config or mentor_config()
    journal = JournalStore(cfg, db_path=str(tmp_path / "webhook.sqlite3"))
    risk = RiskManager(cfg["risk"])
    mentor = BullMentorEngine(cfg, journal, risk)
    engine = TradingViewWebhookEngine(cfg)
    engine.journal = journal
    engine.mentor = mentor
    engine.mentor_enabled = True
    return engine


def test_mentor_pnl_attribution_buckets_losses_by_cause(tmp_path):
    engine = build_webhook_engine_with_journal(tmp_path)
    timestamp = datetime.now(timezone.utc).isoformat()
    engine.journal.record_decision(snapshot("loss-sizing", timestamp=timestamp, entry=100, stop=99, qty=500, max_risk=100))
    engine.journal.record_decision({**snapshot("loss-location", timestamp=timestamp, entry=100, stop=99, qty=50), "location": None})
    engine.journal.record_trade_outcome({"timestamp": timestamp, "alert_ref": "loss-sizing", "symbol": "SPY", "status": "closed", "terminal": True, "pnl": -200, "r_multiple": -2.0})
    engine.journal.record_trade_outcome({"timestamp": timestamp, "alert_ref": "loss-location", "symbol": "SPY", "status": "closed", "terminal": True, "pnl": -50, "r_multiple": -1.0})

    payload = engine.mentor_pnl_attribution_payload(days=30)
    buckets = {item["bucket"]: item for item in payload["attribution"]["buckets"]}

    assert payload["ok"] is True
    assert payload["attribution"]["closed_trades"] == 2
    assert "risk_sizing_issue" in buckets
    assert "setup_quality_issue" in buckets


def test_mentor_strategy_drift_detects_behavior_shift(tmp_path):
    engine = build_webhook_engine_with_journal(tmp_path)
    now = datetime.now(timezone.utc)
    for index in range(8):
        engine.journal.record_decision(snapshot(f"base-{index}", timestamp=(now - timedelta(days=45 + index)).isoformat(), symbol="SPY", qty=10, entry=100, stop=99))
    for index in range(8):
        engine.journal.record_decision(snapshot(f"cur-{index}", timestamp=(now - timedelta(days=index)).isoformat(), symbol="QQQ", qty=80, entry=100, stop=95))

    payload = engine.mentor_strategy_drift_payload(recent_days=30, baseline_days=60)

    assert payload["ok"] is True
    assert payload["drift"]["flags"]
    assert any(item["metric"] in {"avg_qty", "top_symbol", "avg_stop_pct"} for item in payload["drift"]["flags"])


def test_mentor_regime_catalyst_guardrail_uses_connected_bars_and_calendar(tmp_path, monkeypatch):
    engine = build_webhook_engine_with_journal(tmp_path)
    now = datetime.now(timezone.utc)
    bars = [
        Bar(timestamp=now - timedelta(minutes=5 * (60 - idx)), open=100 + idx * 0.05, high=101 + idx * 0.05, low=99 + idx * 0.05, close=100.2 + idx * 0.05, volume=1000)
        for idx in range(60)
    ]
    monkeypatch.setattr(engine, "_fetch_mentor_chart_bars_with_source", lambda **kwargs: (bars, "test_bars", [{"source": "test_bars", "ok": True, "rows": len(bars)}]))
    monkeypatch.setattr(engine, "calendar_month", lambda: {"timeline": [{"date": now.date().isoformat(), "kind": "macro", "title": "Fed decision", "importance": "high"}], "earnings": []})

    payload = engine.mentor_regime_catalyst_payload(symbol="SPY", timeframe="5Min")

    assert payload["ok"] is True
    assert payload["guardrail"]["status"] in {"yellow", "red"}
    assert "high_impact_calendar" in payload["guardrail"]["blockers"]
    assert payload["guardrail"]["regime"]["source"] == "test_bars"


def test_mentor_cross_bot_risk_mirror_flags_overlap(tmp_path, monkeypatch):
    engine = build_webhook_engine_with_journal(tmp_path)
    monkeypatch.setattr(engine, "_positions_snapshot", lambda: ([{"symbol": "SPY", "side": "long", "qty": "10", "current_price": "100"}], None))
    monkeypatch.setattr(engine, "_mentor_external_risk_sources", lambda: [{"name": "Bull Pilot", "ok": True, "positions": [{"symbol": "SPY", "side": "long", "qty": "5", "current_price": "100"}]}])

    payload = engine.mentor_cross_bot_risk_payload()

    assert payload["ok"] is True
    assert payload["mirror"]["warnings"]
    assert payload["mirror"]["warnings"][0]["reason"] == "same_direction_cross_bot_overlap"


def test_mentor_replay_lab_finds_first_invalidation(tmp_path, monkeypatch):
    engine = build_webhook_engine_with_journal(tmp_path)
    timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    engine.journal.record_decision(snapshot("replay-loss", timestamp=timestamp.isoformat(), entry=100, stop=99, qty=100))
    bars = [
        {"timestamp": (timestamp + timedelta(minutes=5)).isoformat(), "open": 100, "high": 100.5, "low": 99.5, "close": 100.1, "volume": 1000},
        {"timestamp": (timestamp + timedelta(minutes=10)).isoformat(), "open": 100.1, "high": 100.2, "low": 98.9, "close": 99.0, "volume": 1200},
    ]
    monkeypatch.setattr(engine, "_fetch_autopsy_bars", lambda decision: bars)

    payload = engine.mentor_replay_lab_payload(alert_ref="replay-loss")

    assert payload["ok"] is True
    assert payload["lab"]["first_invalid"]["index"] == 2
    assert "Stop/invalidation" in payload["lab"]["first_invalid"]["reason"]


def test_mentor_intelligence_endpoints_are_available(monkeypatch):
    app = create_app(mentor_config())
    engine = app.state.engine
    now = datetime.now(timezone.utc)
    bars = [
        Bar(timestamp=now, open=100, high=101, low=99, close=100.5, volume=1000)
        for _ in range(80)
    ]
    monkeypatch.setattr(engine, "_fetch_mentor_chart_bars_with_source", lambda **kwargs: (bars, "test_bars", [{"source": "test_bars", "ok": True, "rows": len(bars)}]))
    monkeypatch.setattr(engine, "_positions_snapshot", lambda: ([], None))
    monkeypatch.setattr(engine, "calendar_month", lambda: {"timeline": [], "earnings": []})
    client = TestClient(app)

    for path in (
        "/api/mentor/pnl-attribution?days=30",
        "/api/mentor/strategy-drift?recent_days=30&baseline_days=60",
        "/api/mentor/regime-catalyst?symbol=SPY&timeframe=5Min",
        "/api/mentor/cross-bot-risk",
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert response.json()["ok"] is True


def test_mentor_safe_daily_root_cause_uses_existing_signals(tmp_path, monkeypatch):
    engine = build_webhook_engine_with_journal(tmp_path)
    timestamp = datetime.now(timezone.utc).isoformat()
    engine.journal.record_decision(snapshot("root-loss", timestamp=timestamp, entry=100, stop=99, qty=300, max_risk=100))
    engine.journal.record_trade_outcome(
        {"timestamp": timestamp, "alert_ref": "root-loss", "symbol": "SPY", "status": "closed", "terminal": True, "pnl": -220, "r_multiple": -2.2}
    )
    monkeypatch.setattr(engine, "mentor_chart_source_health_payload", lambda *args, **kwargs: {"ok": True, "health": {"status": "green", "readback": "test source ok"}})
    monkeypatch.setattr(engine, "_positions_snapshot", lambda: ([], None))

    payload = engine.mentor_daily_root_cause_payload()

    assert payload["ok"] is True
    assert payload["brief"]["advisory_only"] is True
    assert payload["brief"]["evidence"][0]["signal"] == "pnl_primary_drag"
    assert "Daily root cause" in payload["brief"]["headline"]


def test_mentor_trade_quality_heatmap_grades_symbol_setup_buckets(tmp_path):
    engine = build_webhook_engine_with_journal(tmp_path)
    now = datetime.now(timezone.utc)
    for index, pnl in enumerate([120, 90, -40, -80]):
        ref = f"heat-{index}"
        engine.journal.record_decision(snapshot(ref, timestamp=(now - timedelta(days=index)).isoformat(), symbol="SPY", entry=100, stop=99))
        engine.journal.record_trade_outcome(
            {
                "timestamp": (now - timedelta(days=index)).isoformat(),
                "alert_ref": ref,
                "symbol": "SPY",
                "status": "closed",
                "terminal": True,
                "pnl": pnl,
                "r_multiple": pnl / 100,
                "setup": "elephant_bar",
            }
        )

    payload = engine.mentor_trade_quality_heatmap_payload(days=90)

    assert payload["ok"] is True
    assert payload["heatmap"]["closed_trades"] == 4
    assert payload["heatmap"]["rows"]
    assert payload["heatmap"]["rows"][0]["symbol"] == "SPY"
    assert payload["heatmap"]["advisory_only"] is True


def test_mentor_guardrail_do_not_touch_is_read_only_and_no_conflict(tmp_path, monkeypatch):
    engine = build_webhook_engine_with_journal(tmp_path)
    timestamp = datetime.now(timezone.utc).isoformat()
    engine.journal.record_decision(snapshot("guard-loss", timestamp=timestamp, qty=300, max_risk=100))
    engine.journal.record_trade_outcome(
        {"timestamp": timestamp, "alert_ref": "guard-loss", "symbol": "SPY", "status": "closed", "terminal": True, "pnl": -250, "r_multiple": -2.5}
    )
    monkeypatch.setattr(engine, "mentor_chart_source_health_payload", lambda *args, **kwargs: {"ok": True, "health": {"status": "green"}})

    payload = engine.mentor_guardrail_do_not_touch_payload()

    assert payload["ok"] is True
    assert payload["report"]["read_only"] is True
    assert payload["report"]["changes_applied"] is False
    assert payload["report"]["conflicts_with_guardrails"] is False
    assert any(item["key"] == "risk.max_open_positions" for item in payload["report"]["rules"])


def test_mentor_broker_reconciliation_is_read_only_score(tmp_path, monkeypatch):
    engine = build_webhook_engine_with_journal(tmp_path)
    monkeypatch.setattr(engine, "_positions_snapshot", lambda: ([{"symbol": "SPY", "qty": "10", "side": "long", "current_price": "100"}], None))
    monkeypatch.setattr(engine, "lifecycle_payload", lambda **kwargs: {"ok": False, "reason": "No broker reconciliation snapshot has run yet."})

    payload = engine.mentor_broker_reconciliation_payload()

    assert payload["ok"] is True
    assert payload["score"]["read_only"] is True
    assert payload["score"]["changes_applied"] is False
    assert payload["score"]["conflicts_with_guardrails"] is False
    assert payload["score"]["score"] < 100
    assert any(check["name"] == "Position claim linkage" for check in payload["score"]["checks"])


def test_mentor_bot_parity_matrix_is_honest_without_external_source(tmp_path, monkeypatch):
    engine = build_webhook_engine_with_journal(tmp_path)
    monkeypatch.setattr(engine, "_mentor_external_risk_sources", lambda: [])

    payload = engine.mentor_bot_parity_matrix_payload()

    assert payload["ok"] is True
    assert payload["matrix"]["read_only"] is True
    assert payload["matrix"]["status"] == "yellow"
    assert any(row["bull_pilot"] == "not_configured" for row in payload["matrix"]["rows"])


def test_mentor_last_good_week_delta_compares_latest_to_positive_week(tmp_path):
    engine = build_webhook_engine_with_journal(tmp_path)
    now = datetime.now(timezone.utc)
    good_week_anchor = now - timedelta(days=21)
    good_week = good_week_anchor - timedelta(days=good_week_anchor.date().weekday())
    for index, pnl in enumerate([100, 120, 80]):
        ref = f"good-week-{index}"
        ts = (good_week + timedelta(days=index)).isoformat()
        engine.journal.record_decision(snapshot(ref, timestamp=ts))
        engine.journal.record_trade_outcome({"timestamp": ts, "alert_ref": ref, "symbol": "SPY", "status": "closed", "terminal": True, "pnl": pnl, "r_multiple": pnl / 100})
    for index, pnl in enumerate([-120, 60, -90]):
        ref = f"bad-week-{index}"
        ts = (now - timedelta(days=index)).isoformat()
        engine.journal.record_decision(snapshot(ref, timestamp=ts))
        engine.journal.record_trade_outcome({"timestamp": ts, "alert_ref": ref, "symbol": "SPY", "status": "closed", "terminal": True, "pnl": pnl, "r_multiple": pnl / 100})

    payload = engine.mentor_last_good_week_delta_payload(lookback_days=180)

    assert payload["ok"] is True
    assert payload["delta"]["last_good_week"] is not None
    assert payload["delta"]["delta"]["pnl"] < 0
    assert payload["delta"]["advisory_only"] is True


def test_mentor_drill_scheduler_recommends_and_can_create_drill(tmp_path, monkeypatch):
    engine = build_webhook_engine_with_journal(tmp_path)
    timestamp = datetime.now(timezone.utc).isoformat()
    engine.journal.record_decision(snapshot("scheduler-loss", timestamp=timestamp, qty=300, max_risk=100))
    engine.journal.record_trade_outcome(
        {"timestamp": timestamp, "alert_ref": "scheduler-loss", "symbol": "SPY", "status": "closed", "terminal": True, "pnl": -220, "r_multiple": -2.2}
    )
    monkeypatch.setattr(engine, "mentor_chart_source_health_payload", lambda *args, **kwargs: {"ok": True, "health": {"status": "green"}})
    monkeypatch.setattr(engine, "_positions_snapshot", lambda: ([], None))

    preview = engine.mentor_drill_scheduler_payload(auto_create=False)
    created = engine.mentor_drill_scheduler_payload(auto_create=True)

    assert preview["scheduler"]["created"] is None
    assert created["scheduler"]["created"]["status"] == "active"
    assert created["scheduler"]["active_drills"]


def test_mentor_safe_enhancement_endpoints_are_available(monkeypatch):
    app = create_app(mentor_config())
    engine = app.state.engine
    now = datetime.now(timezone.utc)
    bars = [Bar(timestamp=now, open=100, high=101, low=99, close=100.5, volume=1000) for _ in range(80)]
    monkeypatch.setattr(engine, "_fetch_mentor_chart_bars_with_source", lambda **kwargs: (bars, "test_bars", [{"source": "test_bars", "ok": True, "rows": len(bars)}]))
    monkeypatch.setattr(engine, "_positions_snapshot", lambda: ([], None))
    monkeypatch.setattr(engine, "calendar_month", lambda: {"timeline": [], "earnings": []})
    client = TestClient(app)

    for path in (
        "/api/mentor/daily-root-cause",
        "/api/mentor/trade-quality-heatmap?days=90",
        "/api/mentor/guardrail-do-not-touch",
        "/api/mentor/broker-reconciliation",
        "/api/mentor/bot-parity",
        "/api/mentor/last-good-week-delta?lookback_days=180",
        "/api/mentor/drill-scheduler",
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert response.json()["ok"] is True
