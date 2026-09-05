from datetime import datetime, timedelta, timezone
import sqlite3

from bot.core.decision_intelligence import (
    RiskExecutionPlanner,
    TradeReadinessEngine,
    annotation_payload,
    classify_missed_trades,
    discipline_score,
    performance_intelligence,
    readiness_evidence,
)
from bot.core.feature_registry import entitlement_payload, feature_allowed, premium_feature_for_path
from bot.core.playbook import searchable_playbook
from bot.core.risk import RiskManager
from bot.journal_store import JournalStore


NOW = datetime(2026, 9, 4, 16, 0, tzinfo=timezone.utc)


def risk_config():
    return {
        "risk_per_trade": 0.005,
        "max_dollar_risk_per_trade": 1000,
        "max_daily_loss_pct": 0.02,
        "max_consecutive_losses": 3,
        "max_open_positions": 5,
        "max_leverage": 2,
        "max_order_qty": 10000,
        "circuit_breaker_atr_pct": 8.0,
        "planner_max_spread_bps": 20,
    }


def valid_decision(**overrides):
    payload = {
        "timestamp": (NOW - timedelta(seconds=30)).isoformat(),
        "alert_ref": "READY-1",
        "status": "proposed",
        "reason": "execution_disabled",
        "symbol": "SPY",
        "side": "buy",
        "play": "elephant_bar",
        "entry_price": 100,
        "stop_price": 99,
        "take_profit_price": 102,
        "max_dollar_risk": 500,
        "confidence_receipt": {"score": 90, "summary": "Verified setup receipt."},
    }
    payload.update(overrides)
    return payload


def top_down(daily="bullish", weekly="bullish", status="active"):
    return {
        "ok": True,
        "version": "top_down_brain_v1",
        "generated_at": (NOW - timedelta(seconds=20)).isoformat(),
        "daily_bias": {"label": daily},
        "weekly_bias": {"label": weekly},
        "strategy_activation": {"status": status, "reason": "Verified top-down fit."},
    }


def test_readiness_is_deterministic_explainable_and_configuration_driven():
    config = {"trade_readiness": {"weights": {"setup_quality": 1, "guardrail_state": 1}}}
    engine = TradeReadinessEngine(config)
    evidence = readiness_evidence(
        valid_decision(),
        top_down=top_down(),
        risk_state={"ok": True, "timestamp": NOW.isoformat(), "broker_daily_pnl": {"ok": True}},
        calendar={"timestamp": NOW.isoformat(), "events": [], "earnings": []},
        now=NOW,
    )
    first = engine.score(evidence, now=NOW)
    second = engine.score(evidence, now=NOW)

    assert first == second
    assert 0 <= first["score"] <= 100
    assert first["confidence"] == 100
    assert first["advisory_only"] is True
    assert all(item["reason"] and item["why_this_matters"] for item in first["components"])
    assert engine.weights["setup_quality"] > engine.weights["data_freshness"]


def test_readiness_missing_stale_conflicting_and_boundary_inputs_are_honest():
    engine = TradeReadinessEngine({})
    missing = engine.score(readiness_evidence({}, now=NOW), now=NOW)
    assert missing["confidence"] < 50
    assert "setup_quality" in missing["unknown_components"]

    stale_conflict = readiness_evidence(
        valid_decision(timestamp=(NOW - timedelta(hours=2)).isoformat()),
        top_down=top_down(daily="bullish", weekly="bearish"),
        now=NOW,
    )
    scored = engine.score(stale_conflict, now=NOW)
    components = {item["key"]: item for item in scored["components"]}
    assert components["data_freshness"]["score"] == 0
    assert components["regime_alignment"]["status"] == "conflict"

    bounded = engine.score({key: {"score": 1000, "reason": "edge"} for key in engine.weights}, now=NOW)
    assert bounded["score"] == 100
    blocked = engine.score(readiness_evidence(valid_decision(status="rejected", reason="max_open_positions"), now=NOW), now=NOW)
    assert blocked["authoritative_blocked"] is True


def planner():
    cfg = risk_config()
    return RiskExecutionPlanner(RiskManager(cfg), cfg)


def valid_plan(**overrides):
    payload = {
        "symbol": "SPY",
        "direction": "buy",
        "planned_entry": 100,
        "stop": 99,
        "target_one": 102,
        "target_two": 103,
        "invalidation_reason": "Structure fails below the trigger bar.",
    }
    payload.update(overrides)
    return payload


def test_planner_uses_authoritative_risk_and_never_exposes_submit_capability():
    result = planner().plan(
        valid_plan(),
        account={"equity": 100000, "buying_power": 200000},
        positions=[],
        correlation={"ok": True},
        quote_state={"ok": True, "timestamp": NOW.isoformat(), "spread_bps": 4, "source": "broker_quote"},
        endpoint="Alpaca paper",
        approval_state="required",
        now=NOW,
    )
    assert result["ok"] is True
    assert result["risk"]["maximum_planned_loss"] == 500
    assert result["risk"]["calculated_position_size"] == 500
    assert result["risk"]["estimated_loss_at_stop"] == 500
    assert result["plan"]["target_one_r"] == 2
    assert result["can_stage"] is False and result["can_submit"] is False
    assert result["endpoint"] == "Alpaca paper"


def test_planner_blocks_invalid_values_unavailable_equity_stale_quotes_and_volatility():
    invalid = planner().plan(
        valid_plan(planned_entry=0, stop=-1, invalidation_reason=""),
        account={},
        now=NOW,
    )
    codes = {item["code"] for item in invalid["errors"]}
    assert {"invalid_entry", "invalid_stop", "missing_invalidation", "equity_unavailable"} <= codes
    assert invalid["outcome"] == "skip_trade"

    stale = planner().plan(
        valid_plan(),
        account={"equity": 100000, "buying_power": 200000},
        quote_state={"ok": True, "timestamp": (NOW - timedelta(minutes=10)).isoformat(), "spread_bps": 4},
        now=NOW,
    )
    assert "stale_quote" in {item["code"] for item in stale["errors"]}

    volatile = planner().plan(valid_plan(atr_percent=12), account={"equity": 100000}, now=NOW)
    assert "extreme_volatility" in {item["code"] for item in volatile["errors"]}


def test_planner_fractional_estimate_and_maximum_risk_boundary_round_down():
    result = planner().plan(
        valid_plan(planned_entry=100, stop=97.3, target_one=105.4, target_two=108.1, allow_fractional=True),
        account={"equity": 10000, "buying_power": 50000},
        correlation={"ok": True},
        now=NOW,
    )
    assert result["ok"] is True
    assert result["risk"]["fractional_estimate"] is True
    assert result["risk"]["calculated_position_size"] == 18.5185
    assert result["risk"]["estimated_loss_at_stop"] <= result["risk"]["maximum_planned_loss"]


def sample_evidence():
    decisions = []
    outcomes = []
    reviews = []
    pnls = [100, -50, 200, -100, 50, 25]
    rs = [1, -0.5, 2, -1, 0.5, 0.25]
    for index, (pnl, r_value) in enumerate(zip(pnls, rs)):
        ref = f"T-{index}"
        timestamp = (NOW - timedelta(days=index)).isoformat()
        decisions.append(valid_decision(alert_ref=ref, timestamp=timestamp, symbol="SPY" if index % 2 == 0 else "QQQ", play="elephant_bar" if index < 3 else "buy_setup"))
        outcomes.append({"alert_ref": ref, "timestamp": timestamp, "symbol": decisions[-1]["symbol"], "status": "closed", "pnl": pnl, "r_multiple": r_value})
        if index < 5:
            reviews.append({"alert_ref": ref, "strategy": decisions[-1]["play"], "stop_followed": index != 3, "authorized_setup": True})
    return decisions, outcomes, reviews


def test_performance_metrics_use_persisted_records_and_document_formulas():
    decisions, outcomes, reviews = sample_evidence()
    result = performance_intelligence(decisions, outcomes, reviews, now=NOW, minimum_sample=5)

    assert result["sample_size"] == 6
    assert result["overall"]["win_rate"] == round(4 / 6 * 100, 2)
    assert result["overall"]["expectancy_r"] == 0.375
    assert result["overall"]["average_win"] == 93.75
    assert result["overall"]["average_loss"] == -75
    assert result["overall"]["profit_factor"] == 2.5
    assert result["overall"]["max_drawdown"] == 100
    assert result["rolling_windows"]["7"]["sample_size"] == 6
    assert {row["key"] for row in result["breakdowns"]["symbol"]} == {"QQQ", "SPY"}
    assert "profit_factor" in result["formulas"]


def test_performance_withholds_fake_precision_for_small_or_missing_samples():
    result = performance_intelligence([], [], now=NOW)
    assert result["sufficient_sample"] is False
    assert result["overall"]["win_rate"] is None
    assert result["warning"].startswith("Insufficient sample")


def test_missed_trade_categories_require_evidence_and_default_to_insufficient():
    decisions = [
        valid_decision(alert_ref="INTENT"),
        valid_decision(alert_ref="MISSED"),
        valid_decision(alert_ref="BLOCK", status="rejected", reason="max_open_positions"),
        valid_decision(alert_ref="INVALID", status="rejected", reason="invalid_location"),
        valid_decision(alert_ref="UNKNOWN", status="proposed"),
    ]
    reviews = [
        {"alert_ref": "INTENT", "skip_classification": "valid_setup_intentionally_skipped"},
        {"alert_ref": "MISSED", "skip_classification": "valid_setup_missed"},
    ]
    result = classify_missed_trades(decisions, [], reviews, now=NOW)
    by_ref = {item["alert_ref"]: item["category"] for item in result["items"]}
    assert by_ref == {
        "INTENT": "valid_setup_intentionally_skipped",
        "MISSED": "valid_setup_missed",
        "BLOCK": "setup_blocked_by_risk",
        "INVALID": "invalid_setup_correctly_avoided",
        "UNKNOWN": "setup_lacking_sufficient_data",
    }


def test_discipline_score_is_sample_gated_transparent_and_separate_from_profit():
    decisions, outcomes, reviews = sample_evidence()
    result = discipline_score(decisions, outcomes, reviews, now=NOW, minimum_sample=5)
    assert result["score"] is not None
    assert result["profitability_separate"] is True
    assert all("sample_size" in item and "recommendation" in item for item in result["components"])
    thin = discipline_score(decisions[:1], outcomes[:1], reviews[:1], now=NOW, minimum_sample=5)
    assert thin["score"] is None
    assert thin["label"] == "Insufficient evidence"


def test_annotations_use_adjacent_layer_and_only_verified_levels():
    result = annotation_payload(
        valid_decision(invalidation_reason="Below the trigger bar."),
        {"symbol": "SPY", "updated_at": NOW.isoformat(), "key_levels": [{"label": "Prior high", "price": 105}]},
    )
    assert result["render_mode"] == "synchronized_adjacent_layer"
    assert {item["kind"] for item in result["levels"]} >= {"entry", "stop", "target", "key_level"}
    assert result["tradingview_url"].endswith("SPY")


def test_playbook_is_searchable_and_marks_unverified_examples_unavailable():
    full = searchable_playbook()
    assert full["count"] == 11
    filtered = searchable_playbook(query="66%")
    assert [item["id"] for item in filtered["entries"]] == ["tail_reversal"]
    assert filtered["entries"][0]["examples"] == []
    assert "Unavailable" in filtered["entries"][0]["example_state"]


def test_server_feature_registry_defaults_owner_to_pro_and_fails_closed(monkeypatch):
    monkeypatch.delenv("VELEZ_DASHBOARD_TIER", raising=False)
    assert entitlement_payload()["tier"] == "pro"
    assert feature_allowed("pro_console") is True
    monkeypatch.setenv("VELEZ_DASHBOARD_TIER", "core")
    assert feature_allowed("pro_console") is False
    assert feature_allowed("essential_risk") is True
    assert feature_allowed("unknown_feature") is False
    assert premium_feature_for_path("/api/mentor/today") == "coach_intelligence"
    assert premium_feature_for_path("/api/mentor/guardrail-do-not-touch") is None


def test_additive_review_and_note_storage_preserves_existing_database(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE runtime_settings (key TEXT PRIMARY KEY, value_json TEXT NOT NULL, updated_at TEXT NOT NULL)")
        db.execute("INSERT INTO runtime_settings VALUES ('legacy.flag', 'true', '2026-01-01T00:00:00+00:00')")

    journal = JournalStore({"symbols": []}, db_path=str(path))
    review = journal.upsert_trade_review(
        "A-1",
        {
            "strategy": "elephant_bar",
            "setup_tags": ["A setup", "20 SMA"],
            "rule_followed": True,
            "rule_broken": [],
            "actual_entry": 100.25,
            "actual_exit": 102,
            "stop_followed": True,
            "authorized_setup": True,
            "notes": "Stayed inside the plan.",
        },
    )
    note = journal.upsert_symbol_note(
        "spy",
        {
            "thesis": "Hold above prior structure.",
            "catalyst": "Known event only.",
            "key_levels": [{"label": "Prior high", "price": 105}],
            "risks": ["Breadth divergence"],
            "invalidation": "Close below 99.",
        },
    )

    assert journal.get_setting("legacy.flag") is True
    assert journal.trade_review("A-1")["actual_entry"] == 100.25
    assert journal.trade_reviews()[0]["source"] == "authenticated_operator_review"
    assert review["setup_tags"] == ["A setup", "20 SMA"]
    assert journal.symbol_note("SPY")["key_levels"][0]["price"] == 105
    assert journal.symbol_notes()[0]["source"] == "authenticated_private_note"
    assert note["symbol"] == "SPY"
