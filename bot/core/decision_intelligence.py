"""Read-only decision intelligence for Trading Bull Desk.

This module consumes persisted/broker-verified evidence.  It does not import a
broker and has no order-staging or order-submission capability.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence
from urllib.parse import quote
from zoneinfo import ZoneInfo

from .risk import RiskManager


DEFAULT_READINESS_WEIGHTS = {
    "setup_quality": 0.18,
    "strategy_alignment": 0.12,
    "regime_alignment": 0.14,
    "reward_to_risk": 0.14,
    "risk_capacity": 0.14,
    "catalyst_context": 0.10,
    "data_freshness": 0.09,
    "guardrail_state": 0.09,
}


COMPONENT_LABELS = {
    "setup_quality": "Setup quality",
    "strategy_alignment": "Strategy alignment",
    "regime_alignment": "Higher-timeframe / regime alignment",
    "reward_to_risk": "Reward-to-risk",
    "risk_capacity": "Risk capacity",
    "catalyst_context": "Catalyst / context",
    "data_freshness": "Data freshness",
    "guardrail_state": "Guardrail state",
}


def _number(value: Any) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _timestamp(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _clamp_score(value: Any) -> Optional[float]:
    number = _number(value)
    if number is None:
        return None
    return round(max(0.0, min(100.0, number)), 2)


def _clean_text(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").split())[:limit]


class TradeReadinessEngine:
    """Configuration-driven, deterministic advisory score."""

    version = "trade_readiness_v1"

    def __init__(self, config: Mapping[str, Any]) -> None:
        supplied = dict(config.get("trade_readiness", {}).get("weights", {}) or {})
        raw = {key: max(0.0, _number(supplied.get(key, default)) or 0.0) for key, default in DEFAULT_READINESS_WEIGHTS.items()}
        total = sum(raw.values())
        self.weights = {key: value / total for key, value in raw.items()} if total > 0 else dict(DEFAULT_READINESS_WEIGHTS)

    def score(self, evidence: Mapping[str, Mapping[str, Any]], *, now: Optional[datetime] = None) -> dict:
        generated = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        components: List[dict] = []
        weighted_points = 0.0
        available_weight = 0.0
        authoritative_blocked = False
        for key, weight in self.weights.items():
            raw = dict(evidence.get(key, {}) or {})
            score = _clamp_score(raw.get("score"))
            status = str(raw.get("status") or ("unknown" if score is None else "available")).lower()
            reason = _clean_text(raw.get("reason") or ("Input is unavailable." if score is None else "Verified evidence is available."))
            source = _clean_text(raw.get("source") or "Unavailable", 120)
            source_ts = _timestamp(raw.get("timestamp"))
            if score is not None:
                weighted_points += weight * score
                available_weight += weight
            if raw.get("authoritative_block"):
                authoritative_blocked = True
                status = "blocked"
            components.append(
                {
                    "key": key,
                    "label": COMPONENT_LABELS[key],
                    "score": score,
                    "status": status,
                    "weight": round(weight, 4),
                    "weighted_points": round(weight * score, 2) if score is not None else 0.0,
                    "reason": reason,
                    "why_this_matters": _clean_text(raw.get("why_this_matters") or _component_why(key)),
                    "source": source,
                    "timestamp": source_ts.isoformat() if source_ts else None,
                }
            )
        overall = round(max(0.0, min(100.0, weighted_points)))
        confidence = round(available_weight * 100)
        if authoritative_blocked:
            label = "Blocked by an existing guardrail"
        elif confidence < 50:
            label = "Insufficient verified evidence"
        elif overall >= 80:
            label = "High readiness"
        elif overall >= 60:
            label = "Selective readiness"
        else:
            label = "Stand aside and review"
        return {
            "ok": True,
            "version": self.version,
            "timestamp": generated.isoformat(),
            "score": overall,
            "confidence": confidence,
            "label": label,
            "components": components,
            "unknown_components": [item["key"] for item in components if item["score"] is None],
            "authoritative_blocked": authoritative_blocked,
            "advisory_only": True,
            "guardrail": "This score never stages or submits an order and does not replace an existing authoritative risk block.",
        }


def _component_why(key: str) -> str:
    reasons = {
        "setup_quality": "A named pattern still needs verified structure and location before it is actionable.",
        "strategy_alignment": "The detected setup should match the configured Velez play rather than a subjective label.",
        "regime_alignment": "Higher-timeframe and market-wind conflict can reduce follow-through even when the setup itself is valid.",
        "reward_to_risk": "Enough clean reward relative to the stop is needed before account risk is committed.",
        "risk_capacity": "A valid setup is still a skip when configured account or portfolio risk is already consumed.",
        "catalyst_context": "Scheduled catalysts can invalidate normal price-action assumptions or widen execution risk.",
        "data_freshness": "Stale or unverified inputs cannot support a current trading decision.",
        "guardrail_state": "Existing risk, approval, and execution guardrails remain authoritative regardless of this score.",
    }
    return reasons[key]


def readiness_evidence(
    decision: Mapping[str, Any],
    *,
    top_down: Optional[Mapping[str, Any]] = None,
    risk_state: Optional[Mapping[str, Any]] = None,
    calendar: Optional[Mapping[str, Any]] = None,
    now: Optional[datetime] = None,
    fresh_seconds: int = 900,
) -> dict:
    """Normalize existing Desk evidence into readiness components."""

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    receipt = decision.get("confidence_receipt") if isinstance(decision.get("confidence_receipt"), Mapping) else {}
    receipt_score = _clamp_score(receipt.get("score"))
    setup = {
        "score": receipt_score,
        "status": "available" if receipt_score is not None else "unknown",
        "reason": receipt.get("summary") or ("Existing setup confidence receipt is available." if receipt_score is not None else "No verified setup-quality receipt is available."),
        "source": "journal.confidence_receipt" if receipt_score is not None else "Unavailable",
        "timestamp": decision.get("timestamp"),
    }

    top = dict(top_down or {})
    activation = top.get("strategy_activation") if isinstance(top.get("strategy_activation"), Mapping) else {}
    status = str(activation.get("status") or "unknown").lower()
    activation_scores = {"active": 100, "starter": 65, "watch": 35, "inactive": 0}
    strategy_score = activation_scores.get(status)
    strategy = {
        "score": strategy_score,
        "status": "available" if strategy_score is not None else "unknown",
        "reason": activation.get("reason") or "Strategy activation evidence is unavailable.",
        "source": top.get("version") or "Unavailable",
        "timestamp": top.get("generated_at"),
    }

    daily = top.get("daily_bias") if isinstance(top.get("daily_bias"), Mapping) else {}
    weekly = top.get("weekly_bias") if isinstance(top.get("weekly_bias"), Mapping) else {}
    side = str(decision.get("side") or "").lower()
    desired = "bullish" if side == "buy" else "bearish" if side in {"sell", "short"} else ""
    labels = [str(daily.get("label") or "unknown"), str(weekly.get("label") or "unknown")]
    known = [item for item in labels if item != "unknown"]
    if not desired or not known:
        regime_score = None
        regime_status = "unknown"
        regime_reason = "Direction or higher-timeframe bias is unavailable."
    elif all(item == desired for item in known) and len(known) == 2:
        regime_score, regime_status = 100, "aligned"
        regime_reason = f"Daily and weekly bias both align {desired}."
    elif desired in known and len(set(known)) > 1:
        regime_score, regime_status = 45, "conflict"
        regime_reason = f"Daily and weekly bias conflict ({labels[0]} versus {labels[1]})."
    elif any(item == desired for item in known):
        regime_score, regime_status = 65, "partial"
        regime_reason = f"Only part of the available higher-timeframe evidence aligns {desired}."
    else:
        regime_score, regime_status = 20, "opposed"
        regime_reason = f"Available higher-timeframe bias is opposed to the {side or 'unknown'} direction."
    regime = {
        "score": regime_score,
        "status": regime_status,
        "reason": regime_reason,
        "source": top.get("version") or "Unavailable",
        "timestamp": top.get("generated_at"),
    }

    entry = _number(decision.get("entry_price"))
    stop = _number(decision.get("stop_price"))
    target = _number(decision.get("target_two") or decision.get("target_price") or decision.get("take_profit_price"))
    r_value = None
    if entry is not None and stop is not None and target is not None and abs(entry - stop) > 0:
        favorable = target > entry if side == "buy" else target < entry if side in {"sell", "short"} else False
        if favorable:
            r_value = abs(target - entry) / abs(entry - stop)
    rr_score = None if r_value is None else 100 if r_value >= 3 else 80 if r_value >= 2 else 55 if r_value >= 1 else max(0, round(r_value * 50))
    reward = {
        "score": rr_score,
        "status": "available" if rr_score is not None else "unknown",
        "reason": f"Verified target offers {r_value:.2f}R." if r_value is not None else "Entry, stop, and a directionally valid target are required to calculate R.",
        "source": "journal.plan" if r_value is not None else "Unavailable",
        "timestamp": decision.get("timestamp"),
    }

    risk = dict(risk_state or {})
    execution_armed = risk.get("execution_armed")
    daily = risk.get("broker_daily_pnl") if isinstance(risk.get("broker_daily_pnl"), Mapping) else {}
    if risk.get("ok") is True and daily.get("ok") is not False:
        risk_score, risk_status, risk_reason = 100, "available", "Configured risk state and broker equity capacity are available."
    elif risk:
        risk_score, risk_status, risk_reason = 45, "degraded", str(daily.get("reason") or "Risk capacity needs review.")
    else:
        risk_score, risk_status, risk_reason = None, "unknown", "Authoritative risk capacity is unavailable."
    risk_capacity = {
        "score": risk_score,
        "status": risk_status,
        "reason": risk_reason,
        "source": "risk_status" if risk else "Unavailable",
        "timestamp": risk.get("timestamp"),
    }

    calendar_state = dict(calendar or {})
    if not calendar_state:
        catalyst_score, catalyst_status, catalyst_reason = None, "unknown", "Calendar/catalyst context is unavailable."
    else:
        events = list(calendar_state.get("events") or []) + list(calendar_state.get("earnings") or [])
        blocking = [item for item in events if str(item.get("status") or item.get("impact") or item.get("importance") or "").lower() in {"blocked", "high", "critical"}]
        if blocking:
            catalyst_score, catalyst_status = 30, "caution"
            catalyst_reason = f"{len(blocking)} high-impact catalyst item(s) require review."
        else:
            catalyst_score, catalyst_status, catalyst_reason = 100, "clear", "Loaded calendar context contains no explicit blocking item."
    catalyst = {
        "score": catalyst_score,
        "status": catalyst_status,
        "reason": catalyst_reason,
        "source": "calendar_month" if calendar_state else "Unavailable",
        "timestamp": calendar_state.get("timestamp"),
    }

    decision_ts = _timestamp(decision.get("timestamp"))
    age = (current - decision_ts).total_seconds() if decision_ts else None
    if age is None:
        freshness_score, freshness_status, freshness_reason = None, "unknown", "The selected setup has no parseable timestamp."
    elif age < -60:
        freshness_score, freshness_status, freshness_reason = 0, "invalid", "The selected setup timestamp is in the future."
    elif age <= fresh_seconds:
        freshness_score, freshness_status, freshness_reason = 100, "fresh", f"The selected setup is {max(0, int(age))} seconds old."
    elif age <= fresh_seconds * 4:
        freshness_score, freshness_status, freshness_reason = 45, "aging", f"The selected setup is older than the {fresh_seconds}-second freshness target."
    else:
        freshness_score, freshness_status, freshness_reason = 0, "stale", f"The selected setup is stale ({int(age)} seconds old)."
    freshness = {
        "score": freshness_score,
        "status": freshness_status,
        "reason": freshness_reason,
        "source": "journal.timestamp" if decision_ts else "Unavailable",
        "timestamp": decision.get("timestamp"),
    }

    decision_status = str(decision.get("status") or "").lower()
    hard_block = decision_status in {"rejected", "error"}
    if hard_block:
        guard_score, guard_status = 0, "blocked"
        guard_reason = f"Existing decision guardrail blocked the setup: {decision.get('reason') or decision_status}."
    elif decision_status in {"proposed", "submitted", "diagnostic"}:
        guard_score, guard_status, guard_reason = 100, "clear", "The existing decision record contains no authoritative rejection."
    elif decision_status:
        guard_score, guard_status, guard_reason = 50, "review", f"Decision state is {decision_status}; confirm guardrails before proceeding."
    else:
        guard_score, guard_status, guard_reason = None, "unknown", "No existing decision guardrail state is available."
    guardrail = {
        "score": guard_score,
        "status": guard_status,
        "reason": guard_reason,
        "source": "journal.decision",
        "timestamp": decision.get("timestamp"),
        "authoritative_block": hard_block,
    }
    return {
        "setup_quality": setup,
        "strategy_alignment": strategy,
        "regime_alignment": regime,
        "reward_to_risk": reward,
        "risk_capacity": risk_capacity,
        "catalyst_context": catalyst,
        "data_freshness": freshness,
        "guardrail_state": guardrail,
    }


class RiskExecutionPlanner:
    """Structured, non-submitting calculator backed by the existing RiskManager."""

    version = "risk_execution_planner_v1"

    def __init__(self, risk: RiskManager, risk_config: Mapping[str, Any]) -> None:
        self.risk = risk
        self.config = dict(risk_config or {})

    def plan(
        self,
        payload: Mapping[str, Any],
        *,
        account: Optional[Mapping[str, Any]] = None,
        positions: Optional[Sequence[Mapping[str, Any]]] = None,
        correlation: Optional[Mapping[str, Any]] = None,
        quote_state: Optional[Mapping[str, Any]] = None,
        authority_state: Optional[Mapping[str, Any]] = None,
        endpoint: str = "Unknown",
        approval_state: str = "Unknown",
        now: Optional[datetime] = None,
    ) -> dict:
        generated = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        symbol = _clean_text(payload.get("symbol"), 20).upper().replace(" ", "")
        direction = str(payload.get("direction") or payload.get("side") or "").strip().lower()
        if direction == "short":
            direction = "sell"
        entry = _number(payload.get("planned_entry") if "planned_entry" in payload else payload.get("entry_price"))
        stop = _number(payload.get("stop") if "stop" in payload else payload.get("stop_price"))
        target_one = _number(payload.get("target_one"))
        target_two = _number(payload.get("target_two") or payload.get("take_profit_price") or payload.get("target_price"))
        invalidation = _clean_text(payload.get("invalidation_reason"), 500)
        multiplier = _number(payload.get("contract_multiplier")) or 1.0
        allow_fractional = bool(payload.get("allow_fractional")) and multiplier == 1.0
        errors: List[dict] = []
        warnings: List[dict] = []

        def error(code: str, detail: str) -> None:
            errors.append({"code": code, "detail": detail, "why_this_matters": "Impossible or unverifiable plan inputs must be blocked before sizing."})

        def warning(code: str, detail: str, source: str = "planner") -> None:
            warnings.append({"code": code, "detail": detail, "source": source, "why_this_matters": _warning_why(code)})

        if not symbol:
            error("missing_symbol", "Symbol is required.")
        if direction not in {"buy", "sell"}:
            error("invalid_direction", "Direction must be buy or sell.")
        if entry is None or entry <= 0:
            error("invalid_entry", "Planned entry must be a positive number.")
        if stop is None or stop <= 0:
            error("invalid_stop", "Stop must be a positive number.")
        if entry is not None and stop is not None:
            if math.isclose(entry, stop):
                error("zero_stop_distance", "Entry and stop cannot be equal.")
            elif direction == "buy" and stop >= entry:
                error("invalid_long_stop", "A long stop must be below planned entry.")
            elif direction == "sell" and stop <= entry:
                error("invalid_short_stop", "A short stop must be above planned entry.")
        if not invalidation:
            error("missing_invalidation", "A plain-English invalidation reason is required.")
        for name, target in (("target_one", target_one), ("target_two", target_two)):
            if target is None:
                continue
            if target <= 0:
                error(f"invalid_{name}", f"{name.replace('_', ' ').title()} must be positive.")
            elif entry is not None and direction == "buy" and target <= entry:
                error(f"invalid_{name}", f"{name.replace('_', ' ').title()} must be above a long entry.")
            elif entry is not None and direction == "sell" and target >= entry:
                error(f"invalid_{name}", f"{name.replace('_', ' ').title()} must be below a short entry.")

        account_state = dict(account or {})
        equity = _number(account_state.get("equity") or account_state.get("portfolio_value"))
        buying_power = _number(account_state.get("buying_power"))
        if equity is None or equity <= 0:
            error("equity_unavailable", "Broker-confirmed account equity is unavailable.")
        risk_pct = _number(self.config.get("risk_per_trade")) or 0.0
        fixed_cap = _number(self.config.get("max_dollar_risk_per_trade"))
        risk_budget = None if equity is None or equity <= 0 else equity * risk_pct
        if risk_budget is not None and fixed_cap is not None and fixed_cap > 0:
            risk_budget = min(risk_budget, fixed_cap)

        quote = dict(quote_state or {})
        quote_ts = _timestamp(quote.get("timestamp") or quote.get("asof"))
        max_quote_age = max(5, int(_number(payload.get("max_quote_age_seconds")) or 120))
        if quote:
            if quote.get("ok") is False:
                error("quote_unavailable", "The connected quote source did not return a verified quote.")
            elif quote_ts is None:
                warning("quote_timestamp_unknown", "The quote source has no parseable timestamp.", str(quote.get("source") or "quote"))
            else:
                age = (generated - quote_ts).total_seconds()
                if age > max_quote_age:
                    error("stale_quote", f"The connected quote is {int(age)} seconds old; maximum allowed age is {max_quote_age} seconds.")
        else:
            warning("quote_unavailable", "No connected quote was supplied; spread and freshness cannot be confirmed.", "Unavailable")

        spread_bps = _number(quote.get("spread_bps") or payload.get("spread_bps"))
        spread_limit = _number(self.config.get("planner_max_spread_bps")) or 20.0
        if spread_bps is None:
            warning("spread_unknown", "Spread is unavailable; the estimate is not broker-confirmed.", str(quote.get("source") or "Unavailable"))
        elif spread_bps > spread_limit:
            warning("wide_spread", f"Spread is {spread_bps:.2f} bps versus the {spread_limit:.2f} bps planning threshold.", str(quote.get("source") or "quote"))

        atr_percent = _number(payload.get("atr_percent") or quote.get("atr_percent"))
        if self.risk.check_circuit_breaker(atr_percent):
            error("extreme_volatility", f"ATR is {atr_percent:.2f}% and trips the existing volatility circuit breaker.")

        position_rows = list(positions or [])
        same_symbol = [row for row in position_rows if str(row.get("symbol") or "").upper() == symbol]
        if same_symbol:
            warning("existing_position", f"An existing {symbol} position is present; confirm whether this is an authorized add.", "broker_positions")
        correlation_state = dict(correlation or {})
        if correlation_state:
            if correlation_state.get("ok") is False:
                error("correlation_block", str(correlation_state.get("reason") or "Existing correlation limit blocks the plan."))
            elif correlation_state.get("warning"):
                warning("correlation_warning", str(correlation_state.get("reason") or correlation_state.get("warning")), "risk_engine")
        elif position_rows:
            warning("correlation_unknown", "Correlation evidence is unavailable for the current positions.", "Unavailable")
        authority = dict(authority_state or {})
        if authority and authority.get("allowed") is False:
            error("authoritative_risk_block", str(authority.get("reason") or "The existing risk engine blocks this plan."))

        qty: Optional[float] = None
        estimated_loss: Optional[float] = None
        notional: Optional[float] = None
        stop_distance = abs(entry - stop) if entry is not None and stop is not None else None
        if not errors and risk_budget is not None and entry is not None and stop is not None:
            max_qty = int(_number(self.config.get("max_order_qty")) or 10000)
            max_leverage = _number(self.config.get("max_leverage")) or 1.0
            if allow_fractional:
                qty = self.risk.calculate_fixed_risk_fractional_size(
                    max_dollar_risk=risk_budget,
                    entry_price=entry,
                    stop_price=stop,
                    contract_multiplier=multiplier,
                    max_order_qty=max_qty,
                    equity=equity,
                    max_leverage=max_leverage,
                    precision=4,
                )
            else:
                qty = float(
                    self.risk.calculate_fixed_risk_position_size(
                        max_dollar_risk=risk_budget,
                        entry_price=entry,
                        stop_price=stop,
                        contract_multiplier=multiplier,
                        max_order_qty=max_qty,
                        equity=equity,
                        max_leverage=max_leverage,
                    )
                )
            if qty <= 0:
                error("position_size_zero", "The authoritative risk calculation produced a zero position size.")
                qty = None
            else:
                estimated_loss = abs(entry - stop) * qty * multiplier
                notional = entry * qty * multiplier
                if buying_power is None:
                    warning("buying_power_unknown", "Broker buying power is unavailable.", "Unavailable")
                elif notional > buying_power:
                    error("buying_power_exceeded", f"Estimated notional exceeds broker-reported buying power by {notional - buying_power:.2f}.")

        r_one = _target_r(direction, entry, stop, target_one)
        r_two = _target_r(direction, entry, stop, target_two)
        outcome = "skip_trade" if errors else "plan_ready_for_human_review"
        return {
            "ok": not errors,
            "version": self.version,
            "timestamp": generated.isoformat(),
            "outcome": outcome,
            "symbol": symbol or None,
            "direction": direction or None,
            "plan": {
                "planned_entry": entry,
                "stop": stop,
                "invalidation_reason": invalidation or None,
                "target_one": target_one,
                "target_two": target_two,
                "target_one_r": r_one,
                "target_two_r": r_two,
                "contract_multiplier": multiplier,
            },
            "risk": {
                "account_equity": equity,
                "account_equity_source": "broker_account" if equity is not None else "Unavailable",
                "configured_risk_percentage": risk_pct,
                "maximum_planned_loss": round(risk_budget, 2) if risk_budget is not None else None,
                "calculated_position_size": round(qty, 4) if qty is not None else None,
                "fractional_estimate": bool(allow_fractional),
                "estimated_loss_at_stop": round(estimated_loss, 2) if estimated_loss is not None else None,
                "estimated_notional": round(notional, 2) if notional is not None else None,
                "buying_power": buying_power,
                "buying_power_source": "broker_account" if buying_power is not None else "Unavailable",
            },
            "warnings": warnings,
            "errors": errors,
            "approval_state": approval_state,
            "endpoint": endpoint,
            "authority_state": authority or {"allowed": None, "reason": "Unavailable"},
            "estimate_disclosure": "Position size, loss, and R values are calculated estimates. Equity and buying power are broker-confirmed only when their source says broker_account.",
            "can_stage": False,
            "can_submit": False,
            "guardrail": "Planner output is advisory and cannot stage or submit an order. Existing broker and Bull Warden controls remain authoritative.",
        }


def _target_r(direction: str, entry: Optional[float], stop: Optional[float], target: Optional[float]) -> Optional[float]:
    if entry is None or stop is None or target is None or math.isclose(entry, stop):
        return None
    favorable = target > entry if direction == "buy" else target < entry if direction == "sell" else False
    return round(abs(target - entry) / abs(entry - stop), 2) if favorable else None


def _warning_why(code: str) -> str:
    mapping = {
        "spread_unknown": "Unknown spread can make a calculated entry materially different from the fill.",
        "wide_spread": "Wide spreads increase slippage and effective stop risk.",
        "quote_unavailable": "Without a connected quote, freshness and execution quality cannot be verified.",
        "quote_timestamp_unknown": "A quote without time provenance cannot be treated as current.",
        "buying_power_unknown": "Sizing is incomplete until broker buying power is confirmed.",
        "existing_position": "A same-symbol position can turn a new plan into an add and change aggregate risk.",
        "correlation_warning": "Correlated positions can concentrate risk beyond the apparent per-trade amount.",
        "correlation_unknown": "Portfolio concentration cannot be evaluated without correlation evidence.",
    }
    return mapping.get(code, "Review this evidence before committing account risk.")


def build_trade_records(
    decisions: Iterable[Mapping[str, Any]],
    outcomes: Iterable[Mapping[str, Any]],
    reviews: Iterable[Mapping[str, Any]] = (),
) -> List[dict]:
    decision_index = {str(item.get("alert_ref")): dict(item) for item in decisions if item.get("alert_ref")}
    review_index = {str(item.get("alert_ref")): dict(item) for item in reviews if item.get("alert_ref")}
    records: List[dict] = []
    for raw_outcome in outcomes:
        outcome = dict(raw_outcome)
        alert_ref = str(outcome.get("alert_ref") or "")
        decision = decision_index.get(alert_ref, {})
        review = review_index.get(alert_ref, {})
        timestamp = outcome.get("timestamp") or decision.get("timestamp")
        side = str(outcome.get("side") or decision.get("side") or "unknown").lower()
        entry = _number(review.get("actual_entry") or outcome.get("entry_price") or outcome.get("fill_price") or decision.get("entry_price"))
        exit_price = _number(review.get("actual_exit") or outcome.get("exit_price"))
        planned_entry = _number(decision.get("entry_price"))
        planned_stop = _number(decision.get("stop_price"))
        planned_target = _number(decision.get("take_profit_price") or decision.get("target_price"))
        r_multiple = _number(outcome.get("r_multiple"))
        if r_multiple is None and entry is not None and exit_price is not None and planned_stop is not None and not math.isclose(entry, planned_stop):
            movement = exit_price - entry if side == "buy" else entry - exit_price if side in {"sell", "short"} else None
            if movement is not None:
                r_multiple = movement / abs(entry - planned_stop)
        pnl = _number(outcome.get("pnl"))
        top_down = decision.get("top_down") if isinstance(decision.get("top_down"), Mapping) else {}
        regime = outcome.get("regime") or review.get("regime") or (top_down.get("regime") or {}).get("label")
        parsed = _timestamp(timestamp)
        records.append(
            {
                "alert_ref": alert_ref or None,
                "timestamp": parsed.isoformat() if parsed else None,
                "symbol": str(outcome.get("symbol") or decision.get("symbol") or "Unknown").upper(),
                "direction": side,
                "strategy": str(review.get("strategy") or outcome.get("strategy") or outcome.get("setup") or decision.get("play") or "Unknown"),
                "setup_tags": list(review.get("setup_tags") or []),
                "regime": str(regime or "Unknown"),
                "planned": {"entry": planned_entry, "stop": planned_stop, "target": planned_target, "risk": _number(decision.get("max_dollar_risk"))},
                "actual": {"entry": entry, "exit": exit_price, "pnl": pnl, "r_multiple": round(r_multiple, 4) if r_multiple is not None else None},
                "review": review,
                "source": "persisted_trade_outcome_and_journal_decision",
            }
        )
    return sorted(records, key=lambda item: item.get("timestamp") or "")


def performance_intelligence(
    decisions: Iterable[Mapping[str, Any]],
    outcomes: Iterable[Mapping[str, Any]],
    reviews: Iterable[Mapping[str, Any]] = (),
    *,
    now: Optional[datetime] = None,
    minimum_sample: int = 5,
) -> dict:
    generated = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    records = build_trade_records(decisions, outcomes, reviews)
    windows = {}
    for days in (7, 30, 90):
        start = generated - timedelta(days=days)
        selected = [row for row in records if (_timestamp(row.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc)) >= start]
        windows[str(days)] = _metric_block(selected, minimum_sample)
    complete = _metric_block(records, minimum_sample)
    breakdowns = {
        "strategy": _breakdown(records, lambda row: row.get("strategy"), minimum_sample),
        "market_regime": _breakdown(records, lambda row: row.get("regime"), minimum_sample),
        "symbol": _breakdown(records, lambda row: row.get("symbol"), minimum_sample),
        "direction": _breakdown(records, lambda row: row.get("direction"), minimum_sample),
        "time_of_day": _breakdown(records, _time_bucket, minimum_sample),
        "weekday": _breakdown(records, _weekday, minimum_sample),
    }
    return {
        "ok": True,
        "version": "journal_performance_v1",
        "timestamp": generated.isoformat(),
        "sample_size": len(records),
        "minimum_sample": minimum_sample,
        "sufficient_sample": len(records) >= minimum_sample,
        "warning": None if len(records) >= minimum_sample else f"Insufficient sample: {len(records)} of {minimum_sample} required closed records.",
        "overall": complete,
        "rolling_windows": windows,
        "breakdowns": breakdowns,
        "records": list(reversed(records))[:200],
        "formulas": {
            "win_rate": "positive-P/L records / records with known P/L",
            "expectancy_r": "mean of persisted or reconstructable realized R values",
            "average_win_loss": "mean positive/negative persisted dollar P/L",
            "profit_factor": "gross positive P/L / absolute gross negative P/L",
            "drawdown": "largest peak-to-trough decline of chronological cumulative persisted dollar P/L",
        },
        "source": "journal.decisions + journal.trade_outcomes + journal.trade_reviews",
    }


def _metric_block(records: Sequence[Mapping[str, Any]], minimum_sample: int) -> dict:
    pnls = [_number((row.get("actual") or {}).get("pnl")) for row in records]
    pnls = [value for value in pnls if value is not None]
    rs = [_number((row.get("actual") or {}).get("r_multiple")) for row in records]
    rs = [value for value in rs if value is not None]
    wins = [value for value in pnls if value > 0]
    losses = [value for value in pnls if value < 0]
    equity_curve = []
    running = 0.0
    for value in pnls:
        running += value
        equity_curve.append(running)
    peak = 0.0
    max_drawdown = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        max_drawdown = max(max_drawdown, peak - value)
    profit_factor = sum(wins) / abs(sum(losses)) if losses else None
    return {
        "sample_size": len(records),
        "pnl_sample_size": len(pnls),
        "r_sample_size": len(rs),
        "sufficient_sample": len(records) >= minimum_sample,
        "win_rate": round(len(wins) / len(pnls) * 100, 2) if pnls else None,
        "expectancy_r": round(sum(rs) / len(rs), 3) if rs else None,
        "average_win": round(sum(wins) / len(wins), 2) if wins else None,
        "average_loss": round(sum(losses) / len(losses), 2) if losses else None,
        "profit_factor": round(profit_factor, 3) if profit_factor is not None else None,
        "profit_factor_state": "Unavailable: no losing P/L sample." if wins and not losses else "Unavailable" if not pnls else "available",
        "max_drawdown": round(max_drawdown, 2) if pnls else None,
        "net_pnl": round(sum(pnls), 2) if pnls else None,
    }


def _breakdown(records: Sequence[Mapping[str, Any]], key_fn: Any, minimum_sample: int) -> List[dict]:
    groups: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for row in records:
        key = _clean_text(key_fn(row) or "Unknown", 80) or "Unknown"
        groups[key].append(row)
    return [
        {"key": key, **_metric_block(rows, minimum_sample)}
        for key, rows in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
    ]


def _time_bucket(row: Mapping[str, Any]) -> str:
    parsed = _timestamp(row.get("timestamp"))
    if not parsed:
        return "Unknown"
    hour = parsed.astimezone(ZoneInfo("America/New_York")).hour
    if hour < 9:
        return "Pre-market"
    if hour < 11:
        return "Open (09:00–10:59 ET)"
    if hour < 14:
        return "Midday (11:00–13:59 ET)"
    if hour < 16:
        return "Afternoon (14:00–15:59 ET)"
    return "After-hours"


def _weekday(row: Mapping[str, Any]) -> str:
    parsed = _timestamp(row.get("timestamp"))
    return parsed.astimezone(ZoneInfo("America/New_York")).strftime("%A") if parsed else "Unknown"


def classify_missed_trades(
    decisions: Iterable[Mapping[str, Any]],
    outcomes: Iterable[Mapping[str, Any]],
    reviews: Iterable[Mapping[str, Any]] = (),
    *,
    now: Optional[datetime] = None,
    days: int = 30,
) -> dict:
    generated = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff = generated - timedelta(days=max(1, min(int(days), 365)))
    outcome_refs = {str(item.get("alert_ref")) for item in outcomes if item.get("alert_ref")}
    review_index = {str(item.get("alert_ref")): dict(item) for item in reviews if item.get("alert_ref")}
    rows = []
    for raw in decisions:
        decision = dict(raw)
        parsed = _timestamp(decision.get("timestamp"))
        if parsed and parsed < cutoff:
            continue
        ref = str(decision.get("alert_ref") or "")
        if ref and ref in outcome_refs:
            continue
        review = review_index.get(ref, {})
        explicit = str(review.get("skip_classification") or "").lower()
        status = str(decision.get("status") or "").lower()
        reason = str(decision.get("reason") or "").lower()
        if explicit in {"valid_setup_intentionally_skipped", "valid_setup_missed", "invalid_setup_correctly_avoided", "setup_blocked_by_risk", "setup_lacking_sufficient_data"}:
            category = explicit
            explanation = "Classification was explicitly recorded in the authenticated trade review."
        elif status in {"rejected", "error"} and any(token in reason for token in ("risk", "max_", "kill_switch", "correlation", "unprotected", "news_blackout", "approval")):
            category = "setup_blocked_by_risk"
            explanation = f"An existing guardrail blocked the setup: {decision.get('reason') or status}."
        elif status in {"rejected", "ignored"} and any(token in reason for token in ("invalid", "no_signal", "no_setup", "location", "chase", "duplicate")):
            category = "invalid_setup_correctly_avoided"
            explanation = f"The existing setup validation rejected or ignored it: {decision.get('reason') or status}."
        else:
            category = "setup_lacking_sufficient_data"
            explanation = "No outcome or explicit authenticated review proves whether the setup was valid, intentionally skipped, or missed."
        rows.append(
            {
                "alert_ref": ref or None,
                "timestamp": decision.get("timestamp"),
                "symbol": decision.get("symbol"),
                "setup": decision.get("play") or decision.get("reason"),
                "category": category,
                "explanation": explanation,
                "evidence_source": "trade_review" if explicit else "journal_decision",
            }
        )
    counts = Counter(row["category"] for row in rows)
    return {
        "ok": True,
        "version": "missed_trade_review_v1",
        "timestamp": generated.isoformat(),
        "days": days,
        "counts": dict(counts),
        "items": rows[:300],
        "guardrail": "Untraded alerts default to insufficient data; they are never automatically labeled mistakes.",
    }


def discipline_score(
    decisions: Iterable[Mapping[str, Any]],
    outcomes: Iterable[Mapping[str, Any]],
    reviews: Iterable[Mapping[str, Any]] = (),
    *,
    now: Optional[datetime] = None,
    minimum_sample: int = 5,
    max_trades_per_day: int = 5,
) -> dict:
    generated = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    decisions_list = list(decisions)
    outcomes_list = list(outcomes)
    reviews_list = list(reviews)
    review_index = {str(item.get("alert_ref")): dict(item) for item in reviews_list if item.get("alert_ref")}
    records = build_trade_records(decisions_list, outcomes_list, reviews_list)

    components: List[dict] = []

    def add_component(key: str, label: str, good: int, total: int, reason: str, evidence: List[str], recommendation: str) -> None:
        score = round(good / total * 100) if total else None
        components.append(
            {
                "key": key,
                "label": label,
                "score": score,
                "sample_size": total,
                "reason": reason if total else "Unavailable: no measurable evidence.",
                "evidence": evidence[:20],
                "recommendation": recommendation,
            }
        )

    risk_rows = [row for row in decisions_list if _number(row.get("candidate_risk") or row.get("max_dollar_risk")) is not None]
    risk_good = 0
    risk_refs = []
    for row in risk_rows:
        actual = _number(row.get("candidate_risk") or row.get("max_dollar_risk")) or 0.0
        cap = _number(row.get("max_risk_budget") or row.get("max_dollar_risk"))
        followed = cap is None or actual <= cap + 0.01
        risk_good += int(followed)
        if not followed and row.get("alert_ref"):
            risk_refs.append(str(row["alert_ref"]))
    add_component("planned_risk", "Adherence to planned risk", risk_good, len(risk_rows), "Compares recorded candidate risk with its recorded risk budget.", risk_refs, "Size the next reviewed plan inside the recorded risk budget.")

    stop_reviews = [item for item in reviews_list if item.get("stop_followed") is not None]
    stop_good = sum(1 for item in stop_reviews if item.get("stop_followed") is True)
    add_component("stop_discipline", "Stop discipline", stop_good, len(stop_reviews), "Uses authenticated review evidence about whether the planned stop was followed.", [str(item.get("alert_ref")) for item in stop_reviews if item.get("stop_followed") is False], "Document the planned invalidation before entry and review any deviation neutrally.")

    chase_rows = [row for row in decisions_list if "chase" in str(row.get("reason") or "").lower() or row.get("chased") is not None]
    chase_good = sum(1 for row in chase_rows if not bool(row.get("chased")) and "chase" not in str(row.get("reason") or "").lower())
    add_component("no_chasing", "No-chasing discipline", chase_good, len(chase_rows), "Uses explicit chase flags and existing no-chase decision reasons.", [str(row.get("alert_ref")) for row in chase_rows if row.get("alert_ref") and (row.get("chased") or "chase" in str(row.get("reason") or "").lower())], "Wait for the configured retracement or record a valid skip.")

    add_rows = [row for row in decisions_list if str(row.get("play") or "").lower() == "color_change_add" or "add_to_" in str(row.get("reason") or "").lower()]
    add_good = sum(1 for row in add_rows if "loser" not in str(row.get("reason") or "").lower() and row.get("status") != "rejected")
    add_component("adds_to_winners", "Adding only to winners", add_good, len(add_rows), "Uses the existing color-change/add guardrail result.", [str(row.get("alert_ref")) for row in add_rows if row.get("alert_ref") and "loser" in str(row.get("reason") or "").lower()], "Treat a blocked add as a valid protective decision.")

    deviation_reviews = [item for item in reviews_list if item.get("authorized_setup") is not None]
    deviation_good = sum(1 for item in deviation_reviews if item.get("authorized_setup") is True)
    add_component("authorized_setups", "Authorized setup adherence", deviation_good, len(deviation_reviews), "Uses explicit review evidence; setup names alone do not prove a deviation.", [str(item.get("alert_ref")) for item in deviation_reviews if item.get("authorized_setup") is False], "Link every reviewed trade to a playbook entry or document why it was outside the playbook.")

    daily_counts = Counter((_timestamp(row.get("timestamp")) or generated).astimezone(ZoneInfo("America/New_York")).date().isoformat() for row in records)
    day_total = len(daily_counts)
    day_good = sum(1 for count in daily_counts.values() if count <= max_trades_per_day)
    add_component("overtrading", "Trade-frequency discipline", day_good, day_total, f"Compares closed records per day with the configured review threshold of {max_trades_per_day}.", [day for day, count in daily_counts.items() if count > max_trades_per_day], "When the threshold is exceeded, review whether each additional trade was a distinct qualified setup.")

    session_records = [row for row in records if _timestamp(row.get("timestamp"))]
    session_good = 0
    outside_refs = []
    for row in session_records:
        local = _timestamp(row.get("timestamp")).astimezone(ZoneInfo("America/New_York"))  # type: ignore[union-attr]
        inside = local.weekday() < 5 and (local.hour > 9 or (local.hour == 9 and local.minute >= 30)) and local.hour < 16
        session_good += int(inside)
        if not inside and row.get("alert_ref"):
            outside_refs.append(str(row["alert_ref"]))
    add_component("approved_sessions", "Approved-session adherence", session_good, len(session_records), "Uses the default U.S. regular session for evidence; review configured extended-session exceptions separately.", outside_refs, "Confirm the approved session before treating an outside-hours record as a deviation.")

    reviewed_refs = set(review_index)
    outcome_refs = [str(item.get("alert_ref")) for item in outcomes_list if item.get("alert_ref")]
    review_good = sum(1 for ref in outcome_refs if ref in reviewed_refs)
    add_component("review_completion", "Trade review completion", review_good, len(outcome_refs), "Matches persisted outcomes to authenticated structured reviews.", [ref for ref in outcome_refs if ref not in reviewed_refs], "Complete a concise review after the outcome is persisted.")

    intentional = [item for item in reviews_list if item.get("skip_classification") == "valid_setup_intentionally_skipped"]
    skip_good = sum(1 for item in intentional if item.get("valid_skip_followed") is not False)
    add_component("valid_skips", "Following valid skip decisions", skip_good, len(intentional), "Counts only explicit intentional-skip reviews, never all untraded alerts.", [str(item.get("alert_ref")) for item in intentional if item.get("valid_skip_followed") is False], "Keep recording valid skips so patience is measured as positive discipline.")

    available = [item for item in components if item["score"] is not None]
    evidence_sample = len(records)
    overall = round(sum(item["score"] for item in available) / len(available)) if available and evidence_sample >= minimum_sample else None
    recommendations = [item["recommendation"] for item in sorted(available, key=lambda item: item["score"])[:3]]
    return {
        "ok": True,
        "version": "trader_discipline_v1",
        "timestamp": generated.isoformat(),
        "score": overall,
        "sample_size": evidence_sample,
        "minimum_sample": minimum_sample,
        "sufficient_sample": evidence_sample >= minimum_sample and bool(available),
        "label": "Insufficient evidence" if overall is None else "Consistent process" if overall >= 80 else "Developing consistency" if overall >= 60 else "Focused review opportunity",
        "components": components,
        "recommendations": recommendations,
        "profitability_separate": True,
        "profitability": _metric_block(records, minimum_sample),
        "guardrail": "The score measures documented process behavior, not trader worth, and never changes execution permissions.",
    }


def annotation_payload(decision: Mapping[str, Any], note: Optional[Mapping[str, Any]] = None) -> dict:
    symbol = str(decision.get("symbol") or (note or {}).get("symbol") or "").upper().strip()
    source_ts = decision.get("timestamp") or (note or {}).get("updated_at")
    levels = []
    for kind, label, value in (
        ("entry", "Planned entry", decision.get("entry_price")),
        ("stop", "Protective stop", decision.get("stop_price")),
        ("target", "Target one", decision.get("target_one")),
        ("target", "Target two", decision.get("target_two") or decision.get("take_profit_price") or decision.get("target_price")),
    ):
        numeric = _number(value)
        if numeric is not None:
            levels.append({"kind": kind, "label": label, "price": numeric, "source": "journal_decision", "timestamp": source_ts})
    for raw in list((note or {}).get("key_levels") or []):
        numeric = _number(raw.get("price") if isinstance(raw, Mapping) else raw)
        if numeric is not None:
            label = raw.get("label") if isinstance(raw, Mapping) else "Thesis level"
            levels.append({"kind": "key_level", "label": _clean_text(label, 80) or "Thesis level", "price": numeric, "source": "authenticated_symbol_note", "timestamp": (note or {}).get("updated_at")})
    invalidation = _clean_text(decision.get("invalidation_reason") or (note or {}).get("invalidation"), 500)
    return {
        "ok": True,
        "version": "tradingview_annotation_context_v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol or None,
        "levels": levels,
        "invalidation": invalidation or None,
        "tradingview_url": f"https://www.tradingview.com/chart/?symbol={quote(symbol)}" if symbol else None,
        "render_mode": "synchronized_adjacent_layer",
        "guardrail": "Annotations are verified adjacent context; they do not manipulate or obscure the cross-origin TradingView iframe or replace native candles.",
    }
