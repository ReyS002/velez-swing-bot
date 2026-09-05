from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo


class BullMentorEngine:
    """Deterministic coaching analytics over Velez Trading Bot's authoritative journal.

    The mentor can explain and teach, but it is intentionally disconnected from
    broker submission, order approval, and risk mutation. LLM narration is added
    by Winston only after this class has produced the evidence and calculations.
    """

    VERSION = "bull_mentor_v1"
    PROFILE_MODES = {"auto", "retail", "institutional", "prop"}
    EXPERIENCE_LEVELS = {"beginner", "developing", "advanced", "professional"}
    COACHING_STYLES = {
        "concise",
        "detailed",
        "socratic",
        "leo_concise",
        "winston_analyst",
        "prop_risk_officer",
        "velez_drill_sergeant",
    }
    RESPONSE_MODES = {
        "quick": {"word_cap": 45, "allow_markdown": False},
        "coach": {"word_cap": 90, "allow_markdown": False},
        "deep_dive": {"word_cap": 220, "allow_markdown": True},
        "voice_memo": {"word_cap": 140, "allow_markdown": False},
        "trade_replay": {"word_cap": 120, "allow_markdown": False},
    }
    PERSONALITY_DIALS = {
        "concise": "short, direct desk coach",
        "detailed": "clear analyst, but still no essay unless asked",
        "socratic": "ask one sharp reflective question before the action",
        "leo_concise": "Leo concise: warm, sharp, human, no sermon",
        "winston_analyst": "Winston analyst: measured, evidence-first, one practical close",
        "prop_risk_officer": "prop risk officer: capital-defense first, strict on drawdown and sizing",
        "velez_drill_sergeant": "Velez drill sergeant: blunt, disciplined, action-focused",
    }
    TERMINAL_STATUSES = {
        "closed",
        "won",
        "lost",
        "stopped_out",
        "stop_loss",
        "target_hit",
        "take_profit",
        "filled_exit",
        "manual_exit",
        "time_stop_exit",
        "flat",
    }

    def __init__(self, config: dict, journal: Any, risk: Any = None) -> None:
        self.root_config = config
        self.config = config.get("bull_mentor", {})
        self.journal = journal
        self.risk = risk
        timezone_name = str(config.get("timezone", "America/New_York") or "America/New_York")
        if timezone_name == "US/Eastern":
            timezone_name = "America/New_York"
        try:
            self.trading_timezone = ZoneInfo(timezone_name)
        except Exception:
            self.trading_timezone = ZoneInfo("America/New_York")

    def profile(self) -> dict:
        stored = self.journal.mentor_profile() or {}
        defaults = {
            "experience_level": "developing",
            "primary_mode": "auto",
            "coaching_style": "leo_concise",
            "goals": [],
            "focus_areas": ["risk_discipline", "setup_selection", "execution_quality"],
            "local_only": True,
            "updated_at": None,
        }
        return {**defaults, **stored, "local_only": True}

    def update_profile(self, payload: dict) -> dict:
        current = self.profile()
        experience = str(payload.get("experience_level", current["experience_level"])).strip().lower()
        mode = str(payload.get("primary_mode", current["primary_mode"])).strip().lower()
        style = str(payload.get("coaching_style", current["coaching_style"])).strip().lower()
        if experience not in self.EXPERIENCE_LEVELS:
            raise ValueError("experience_level must be beginner, developing, advanced, or professional")
        if mode not in self.PROFILE_MODES:
            raise ValueError("primary_mode must be auto, retail, institutional, or prop")
        if style not in self.COACHING_STYLES:
            raise ValueError(
                "coaching_style must be concise, detailed, socratic, leo_concise, "
                "winston_analyst, prop_risk_officer, or velez_drill_sergeant"
            )

        raw_goals = payload.get("goals", current.get("goals", []))
        if isinstance(raw_goals, str):
            raw_goals = [item.strip() for item in raw_goals.splitlines()]
        goals = [" ".join(str(item).split())[:160] for item in (raw_goals or []) if str(item).strip()][:8]

        raw_focus = payload.get("focus_areas", current.get("focus_areas", []))
        if isinstance(raw_focus, str):
            raw_focus = [item.strip() for item in raw_focus.split(",")]
        focus = [" ".join(str(item).lower().split())[:64] for item in (raw_focus or []) if str(item).strip()][:8]
        updated = {
            "experience_level": experience,
            "primary_mode": mode,
            "coaching_style": style,
            "goals": goals,
            "focus_areas": focus,
            "local_only": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.journal.save_mentor_profile(updated)
        return updated

    def report(
        self,
        *,
        scope: str = "today",
        days: Optional[int] = None,
        alert_ref: str = "",
        now: Optional[datetime] = None,
        persist: bool = False,
    ) -> dict:
        current = self._aware_now(now)
        normalized_scope = str(scope or "today").strip().lower()
        if normalized_scope not in {"today", "weekly", "trade"}:
            raise ValueError("mentor scope must be today, weekly, or trade")

        if normalized_scope == "today":
            local_start = current.astimezone(self.trading_timezone).replace(hour=0, minute=0, second=0, microsecond=0)
        elif normalized_scope == "weekly":
            lookback = max(2, min(int(days or self.config.get("weekly_days", 7)), 90))
            local_start = current.astimezone(self.trading_timezone) - timedelta(days=lookback)
        else:
            local_start = current.astimezone(self.trading_timezone) - timedelta(days=3650)

        start = local_start.astimezone(timezone.utc)
        end = current.astimezone(timezone.utc)
        decisions = self.journal.mentor_decisions_between(start.isoformat(), end.isoformat(), limit=10000)
        outcomes = self.journal.trade_outcomes_between(start.isoformat(), end.isoformat(), limit=10000)
        cleaned_ref = str(alert_ref or "").strip()
        if normalized_scope == "trade":
            decisions = [item for item in decisions if str(item.get("alert_ref") or "") == cleaned_ref]
            outcomes = [item for item in outcomes if str(item.get("alert_ref") or "") == cleaned_ref]

        profile = self.profile()
        mode = self._effective_mode(profile)
        evidence: List[dict] = []
        discipline = self._discipline_metrics(decisions, evidence)
        performance = self._performance_metrics(outcomes)
        execution = self._execution_metrics(decisions, outcomes, evidence)
        prop = self._prop_metrics(decisions, outcomes, evidence)
        scorecards = self._scorecards(
            decisions=decisions,
            discipline=discipline,
            performance=performance,
            execution=execution,
            prop=prop,
            mode=mode,
        )
        patterns = self._patterns(decisions, discipline, performance, execution, prop, mode, evidence)
        period = {"start": start.isoformat(), "end": end.isoformat(), "timezone": str(self.trading_timezone)}
        recommendation = self._recommendation(scorecards, patterns, mode)
        mistake_fingerprint = self._mistake_fingerprint(decisions, outcomes, discipline, execution, patterns, evidence)
        shadow_book = self._shadow_book(decisions, outcomes, evidence)
        pre_trade_challenge = self._pre_trade_challenge(recommendation, mode, decisions)
        institutional_read = self._institutional_read(mode, decisions, execution, prop)
        replay_coach = self._trade_replay_coach(decisions, outcomes) if normalized_scope == "trade" else self._latest_replay_prompt(outcomes)
        personality = self._personality_payload(profile, mode)
        drill = (
            self._persist_drill(recommendation, evidence, period)
            if normalized_scope != "trade"
            else {
                "id": None,
                "status": "preview",
                "title": recommendation.get("title"),
                "instruction": recommendation.get("instruction"),
                "dimension": recommendation.get("dimension"),
                "evidence": self._dedupe_evidence(evidence)[:6],
            }
        )
        sample = self._sample_assessment(decisions, performance, execution)
        headline = self._headline(scorecards, recommendation, sample, normalized_scope)
        report = {
            "ok": True,
            "version": self.VERSION,
            "timestamp": current.astimezone(timezone.utc).isoformat(),
            "scope": normalized_scope,
            "mode": mode,
            "advisory_only": True,
            "profile": profile,
            "period": period,
            "headline": headline,
            "sample": sample,
            "metrics": {
                "discipline": discipline,
                "performance": performance,
                "execution": execution,
                "prop": prop if mode == "prop" else {"applicable": False},
            },
            "scorecards": scorecards,
            "patterns": patterns,
            "mentor_edges": {
                "response_governor": self.governor_policy("", profile=profile),
                "trade_replay_coach": replay_coach,
                "mistake_fingerprint": mistake_fingerprint,
                "shadow_book": shadow_book,
                "pre_trade_challenge": pre_trade_challenge,
                "institutional_mode": institutional_read,
                "one_tap_drill_builder": {
                    "ready": bool(recommendation.get("title")),
                    "title": recommendation.get("title"),
                    "dimension": recommendation.get("dimension"),
                    "instruction": recommendation.get("instruction"),
                },
                "personality_dial": personality,
            },
            "mistake_fingerprint": mistake_fingerprint,
            "shadow_book": shadow_book,
            "pre_trade_challenge": pre_trade_challenge,
            "institutional_read": institutional_read,
            "replay_coach": replay_coach,
            "personality": personality,
            "recommendation": recommendation,
            "drill": drill,
            "active_drills": self.journal.mentor_drills(include_completed=False, limit=8),
            "goals": profile.get("goals", []),
            "evidence": self._dedupe_evidence(evidence)[:20],
            "trade": self._trade_detail(decisions, outcomes) if normalized_scope == "trade" else None,
            "guardrails": {
                "can_submit_orders": False,
                "can_approve_orders": False,
                "can_change_risk": False,
                "facts_from_journal_only": True,
                "minimum_performance_sample": int(self.config.get("minimum_performance_sample", 5)),
            },
        }
        report["report_fingerprint"] = self._fingerprint(
            {
                "scope": report["scope"],
                "mode": report["mode"],
                "period_start": report["period"]["start"][:10],
                "scorecards": report["scorecards"],
                "samples": report["sample"],
            }
        )
        if persist:
            report["report_id"] = self._persist_report_once(report)
        return report

    def set_drill_status(self, drill_id: str, status: str) -> dict:
        updated = self.journal.set_mentor_drill_status(drill_id, status)
        if not updated:
            return {"ok": False, "reason": "mentor_drill_not_found"}
        return {"ok": True, "drill": updated, "active_drills": self.journal.mentor_drills(limit=8)}

    def briefing_script(
        self,
        *,
        kind: str,
        report: dict,
        daily_brief: dict,
        lifecycle: dict,
        risk: dict,
        regime: dict,
    ) -> dict:
        normalized_kind = "morning" if str(kind or "").lower() == "morning" else "evening"
        summary = lifecycle.get("summary", {}) or {}
        pnl = daily_brief.get("calendar", {}).get("pnl", {}) or {}
        profile = risk.get("profile", {}) or {}
        recommendation = report.get("recommendation", {}) or {}
        performance = report.get("metrics", {}).get("performance", {}) or {}
        discipline = report.get("metrics", {}).get("discipline", {}) or {}
        watchlist = [str(item.get("symbol") or "") for item in daily_brief.get("watchlist", []) if item.get("symbol")]
        regime_label = str(regime.get("label") or "unknown").replace("_", " ")
        regime_confidence = self._number(regime.get("confidence"))
        confidence_text = f" at {regime_confidence:.0f} percent confidence" if regime_confidence is not None else ""
        focus = str(recommendation.get("instruction") or "Wait for structure, location, and risk to align.")
        max_risk = self._number(profile.get("max_risk_dollars"))
        risk_pct = self._number(profile.get("max_risk_pct"))

        if normalized_kind == "morning":
            paragraphs = [
                (
                    "Good morning. This is your Velez Mentor pre-market briefing. "
                    f"The current desk regime is {regime_label}{confidence_text}. "
                    f"The active risk profile is {profile.get('mode', report.get('mode', 'retail'))}, "
                    f"with up to {f'${max_risk:,.2f}' if max_risk is not None else 'the configured Bull Matrix limit'} "
                    f"per trade{f', or {risk_pct:.2f} percent' if risk_pct is not None else ''}."
                ),
                (
                    f"The desk is carrying {int(summary.get('open_positions') or 0)} open positions and "
                    f"{int(summary.get('open_orders') or 0)} working orders. "
                    f"Scanner status is {daily_brief.get('scanner', {}).get('mode', 'unknown')}. "
                    f"Primary coverage is {', '.join(watchlist[:8]) or 'not loaded'}."
                ),
                (
                    f"Calendar readiness says {daily_brief.get('calendar', {}).get('session', {}).get('label', 'session timing is still loading')}. "
                    "Before the open, identify the nearest scheduled macro or earnings event, mark the first clean support and resistance locations, "
                    "and decide which symbols are allowed to remain observation-only. A fast market is not permission to skip location."
                ),
                (
                    f"Your current coaching edge is {report.get('headline', 'still collecting evidence')} "
                    f"Today's process commitment is: {focus}"
                ),
                (
                    "For every qualified alert, read the receipt in the same order: setup, market location, invalidation, dollars at risk, "
                    "liquidity, and exit plan. Institutional orders also need an arrival price, participation cap, and child schedule. "
                    "Prop accounts must keep planned size uniform and respect the trailing-drawdown lock without negotiation."
                ),
                (
                    "Treat every alert as a proposal, not a command. Confirm market location, invalidation, "
                    "size, and participation before execution. If any required measurement is missing, stand down and journal the gap. "
                    "Preserve capital first; opportunity is renewable."
                ),
            ]
        else:
            terminal = int(performance.get("terminal_trades") or 0)
            expectancy = performance.get("expectancy_r") if performance.get("sufficient_sample") else None
            month_pl = self._number(pnl.get("month_pl")) or 0.0
            day_pl = self._number(pnl.get("day_pl"))
            paragraphs = [
                (
                    "This is your Velez Mentor closing recap. "
                    f"The desk finished with {terminal} terminal trade{'s' if terminal != 1 else ''} in the review window, "
                    f"{int(summary.get('open_positions') or 0)} positions still open, "
                    f"{f'today P and L of ${day_pl:,.2f}' if day_pl is not None else 'today P and L unavailable'}, "
                    f"and month-to-date P and L of ${month_pl:,.2f}. "
                    f"The closing desk regime is {regime_label}{confidence_text}."
                ),
                (
                    f"Defined-stop discipline was {self._number(discipline.get('defined_stop_rate')) or 0:.0f} percent, "
                    f"and risk-cap adherence was {self._number(discipline.get('risk_cap_adherence_rate')) or 0:.0f} percent. "
                    + (
                        f"Measured expectancy is {float(expectancy):.2f} R."
                        if expectancy is not None
                        else "The closed-trade sample is still too thin for a reliable expectancy claim."
                    )
                ),
                (
                    "Review each new post-trade autopsy without letting P and L rewrite the entry facts. A profitable trade can still contain "
                    "a location, chase, sizing, or execution violation. A losing trade can still be a valid planned loss when structure, "
                    "invalidation, and size were correct. Promote repeatable process, not isolated outcomes."
                ),
                (
                    f"The evidence-backed development edge is: {report.get('headline', 'more journal evidence is needed')} "
                    f"Carry this drill forward: {focus}"
                ),
                (
                    "Before tomorrow, reconcile every terminal fill, label any missing entry chart or arrival price, and confirm that no open "
                    "position is orphaned from its alert reference. Institutional reviews should compare fill ratio, participation, and slippage. "
                    "Prop reviews should compare planned risk with the previous trade and the current drawdown boundary."
                ),
                (
                    "Separate a valid planned loss from a process violation, and never let one profitable result excuse "
                    "undefined risk or weak location. Write one rule you will repeat, close the desk deliberately, and stop optimizing after the fact. "
                    "The journal is the scorekeeper; tomorrow begins flat."
                ),
            ]
        text = " ".join(" ".join(paragraph.split()) for paragraph in paragraphs)
        return {
            "ok": True,
            "kind": normalized_kind,
            "script": text[:2400],
            "estimated_seconds": max(45, min(150, round(len(text.split()) / 2.0))),
            "advisory_only": True,
            "report_fingerprint": report.get("report_fingerprint"),
        }

    def post_trade_autopsy_review(self, autopsy: dict) -> dict:
        """Draft exactly three evidence-backed bullets for a terminal trade."""
        decision = autopsy.get("decision", {}) or {}
        classification = autopsy.get("bar_classification", {}) or {}
        risk = autopsy.get("risk_review", {}) or {}
        outcome = autopsy.get("outcome", {}) or {}
        alert_ref = str(autopsy.get("alert_ref") or decision.get("alert_ref") or "")
        play = str(decision.get("play") or "unclassified setup").replace("_", " ")
        location = str(decision.get("location") or "").replace("_", " ")
        bar_label = str(classification.get("label") or "unavailable").replace("_", " ")
        bar_reason = str(classification.get("reason") or "The linked entry bar could not be verified.")

        if location:
            setup_text = (
                f"The journal labeled this {play} at {location}; the linked entry bar classified as "
                f"{bar_label}. {bar_reason}"
            )
        else:
            setup_text = (
                f"The journal labeled this {play}, but structural location was missing. The linked entry bar classified as "
                f"{bar_label}; location discipline is the first review gap."
            )

        risk_text = str(risk.get("text") or "").strip()
        if not risk_text:
            risk_text = (
                "A verified entry-to-stop risk record was unavailable, so the terminal result cannot override "
                "the risk-control evidence gap."
            )

        value = self._number(outcome.get("r_multiple"))
        if value is None:
            value = self._number(outcome.get("pnl"))
        if not risk.get("defined_risk"):
            lesson_text = "Rehearse entry, invalidation, per-unit risk, and total Bull Matrix risk before the next five proposals."
        elif not decision.get("location"):
            lesson_text = (
                "Replay five alerts and state market location before viewing the outcome; do not promote a setup whose "
                "location was unlabeled."
            )
        elif value is not None and value < 0:
            lesson_text = (
                f"Classify the loss as planned or process-driven: preserve the setup only if the "
                f"{classification.get('label', 'entry bar')} and location rules were valid at entry."
            )
        else:
            lesson_text = (
                f"Preserve the repeatable checks behind the {classification.get('label', 'entry')} and compare the actual "
                "exit with the original target before changing the playbook."
            )

        outcome_id = outcome.get("id")
        bullets = [
            {
                "title": "Setup and location",
                "text": setup_text,
                "evidence": [value for value in (alert_ref, decision.get("journal_id")) if value],
            },
            {
                "title": "Risk and execution",
                "text": risk_text,
                "evidence": [value for value in (alert_ref, outcome_id) if value],
            },
            {
                "title": "Mentor lesson",
                "text": lesson_text,
                "evidence": [alert_ref] if alert_ref else [],
            },
        ]
        return {
            "ok": True,
            "version": self.VERSION,
            "bullets": bullets,
            "summary": " ".join(f"{index + 1}. {item['text']}" for index, item in enumerate(bullets)),
            "advisory_only": True,
            "facts_from_journal_and_market_data_only": True,
        }

    def governor_policy(self, question: str = "", *, profile: Optional[dict] = None, mode: str = "") -> dict:
        """Return the hard answer contract used by both rules and LLM narration."""
        profile = profile or self.profile()
        style = str(profile.get("coaching_style") or "leo_concise").strip().lower()
        normalized = " ".join(str(question or "").lower().split())
        response_mode = "coach"
        if any(token in normalized for token in ("brief", "quick", "one sentence", "short", "no essay")):
            response_mode = "quick"
        if any(token in normalized for token in ("deep", "explain", "why", "break down", "diagnose")):
            response_mode = "deep_dive" if style in {"detailed", "winston_analyst"} else "coach"
        if any(token in normalized for token in ("voice memo", "memo", "read this aloud")):
            response_mode = "voice_memo"
        if any(token in normalized for token in ("replay", "autopsy", "entry candle", "chart", "setup")):
            response_mode = "trade_replay"
        if style in {"leo_concise", "concise", "velez_drill_sergeant", "prop_risk_officer"} and response_mode == "deep_dive":
            response_mode = "coach"
        contract = dict(self.RESPONSE_MODES.get(response_mode, self.RESPONSE_MODES["coach"]))
        if style == "detailed":
            contract["word_cap"] = min(220, max(contract["word_cap"], 140))
            contract["allow_markdown"] = True
        elif style == "socratic":
            contract["word_cap"] = min(contract["word_cap"], 80)
            contract["must_include_question"] = True
        elif style == "velez_drill_sergeant":
            contract["word_cap"] = min(contract["word_cap"], 55)
        elif style == "prop_risk_officer":
            contract["word_cap"] = min(contract["word_cap"], 70)
        elif style == "leo_concise":
            contract["word_cap"] = min(contract["word_cap"], 65)
        return {
            "mode": response_mode,
            "style": style,
            "persona": self.PERSONALITY_DIALS.get(style, self.PERSONALITY_DIALS["leo_concise"]),
            "word_cap": int(contract["word_cap"]),
            "allow_markdown": bool(contract.get("allow_markdown", False)),
            "must_include_question": bool(contract.get("must_include_question", False)),
            "shape": "answer, one evidence reason, one next action",
            "advisory_only": True,
        }

    def govern_reply(self, reply: str, *, question: str = "", report: Optional[dict] = None, policy: Optional[dict] = None) -> dict:
        """Clamp verbosity and remove provider fluff without weakening safety text."""
        report = report or {}
        policy = policy or self.governor_policy(question, profile=report.get("profile") or None)
        text = " ".join(str(reply or "").split())
        text = self._strip_provider_fluff(text)
        if not policy.get("allow_markdown"):
            text = self._plain_text(text)
        cap = max(20, int(policy.get("word_cap") or 90))
        trimmed = False
        if len(text.split()) > cap:
            text = self._trim_to_word_cap(text, cap)
            trimmed = True
        if policy.get("must_include_question") and "?" not in text:
            challenge = (report.get("pre_trade_challenge") or {}).get("question") or "What evidence would make you stand down?"
            text = self._trim_to_word_cap(f"{text} Question: {challenge}", cap)
            trimmed = True
        text = text.strip()
        return {
            "reply": text,
            "policy": policy,
            "word_count": len(text.split()),
            "trimmed": trimmed,
        }

    def rule_answer(self, question: str, report: dict) -> str:
        normalized = " ".join(str(question or "").lower().split())
        recommendation = report.get("recommendation", {})
        metrics = report.get("metrics", {})
        sample = report.get("sample", {})
        if any(word in normalized for word in ("buy", "sell", "approve", "place order", "execute")):
            return (
                "Velez Mentor is advisory only and cannot place, approve, or recommend a live order. "
                f"Your current process focus is: {recommendation.get('title', 'follow the Bull Matrix and wait for qualified structure')}."
            )
        if any(word in normalized for word in ("risk", "size", "drawdown")):
            discipline = metrics.get("discipline", {})
            return (
                f"Risk-discipline score is {self._score_text(report, 'risk_discipline')}. "
                f"Defined-stop rate is {discipline.get('defined_stop_rate', 0):.0f}% and risk-cap adherence is "
                f"{discipline.get('risk_cap_adherence_rate', 0):.0f}%. Next drill: {recommendation.get('instruction', 'review risk receipts')}."
            )
        if any(word in normalized for word in ("execution", "vwap", "twap", "slippage", "participation")):
            execution = metrics.get("execution", {})
            return (
                f"Execution-quality score is {self._score_text(report, 'execution_quality')}. "
                f"{execution.get('planned_parents', 0)} sliced parent orders were observed with "
                f"{execution.get('participation_breaches', 0)} participation-cap breaches. "
                f"Measured slippage sample: {execution.get('slippage_samples', 0)}."
            )
        if any(word in normalized for word in ("performance", "expectancy", "win rate", "progress")):
            performance = metrics.get("performance", {})
            if not performance.get("sufficient_sample"):
                return (
                    f"Only {performance.get('terminal_trades', 0)} terminal outcomes are available; "
                    f"{sample.get('performance', {}).get('note', 'more closed trades are needed before judging expectancy')}."
                )
            return (
                f"Across {performance.get('terminal_trades', 0)} terminal trades, win rate is "
                f"{performance.get('win_rate', 0):.1f}% and expectancy is {performance.get('expectancy_r', 0):.2f}R."
            )
        return f"{report.get('headline', '')} Next action: {recommendation.get('instruction', '')}".strip()

    def build_drill(self, report: dict, *, dimension: str = "", title: str = "", instruction: str = "") -> dict:
        """Create a one-tap drill from the current Mentor report."""
        recommendation = report.get("recommendation", {}) or {}
        selected_dimension = str(dimension or recommendation.get("dimension") or "process_consistency").strip()
        selected_title = " ".join(str(title or recommendation.get("title") or "One-rule session").split())[:240]
        selected_instruction = " ".join(
            str(instruction or recommendation.get("instruction") or "Choose one rule, follow it on every alert, and review after the close.").split()
        )[:2000]
        evidence = report.get("evidence") if isinstance(report.get("evidence"), list) else []
        period = report.get("period") if isinstance(report.get("period"), dict) else {}
        fingerprint = self._fingerprint(
            {
                "kind": "one_tap_drill",
                "period": str(period.get("start") or report.get("timestamp") or "")[:10],
                "dimension": selected_dimension,
                "title": selected_title,
                "instruction": selected_instruction,
            }
        )
        drill = self.journal.upsert_mentor_drill(
            {
                "fingerprint": fingerprint,
                "title": selected_title,
                "instruction": selected_instruction,
                "dimension": selected_dimension,
                "evidence": self._dedupe_evidence(evidence)[:6],
            }
        )
        return {"ok": True, "drill": drill, "active_drills": self.journal.mentor_drills(limit=8)}

    def _mistake_fingerprint(
        self,
        decisions: List[dict],
        outcomes: List[dict],
        discipline: dict,
        execution: dict,
        patterns: List[dict],
        evidence: List[dict],
    ) -> dict:
        leaks: List[dict] = []
        actionable_raw = int(discipline.get("actionable") or 0)
        actionable = max(1, actionable_raw)
        missing_location = 0 if actionable_raw <= 0 else max(0, int(round(actionable * (100 - float(discipline.get("location_rate") or 0)) / 100)))
        missing_stop = 0 if actionable_raw <= 0 else max(0, int(round(actionable * (100 - float(discipline.get("defined_stop_rate") or 0)) / 100)))
        risk_breaks = 0 if actionable_raw <= 0 else max(0, int(round(actionable * (100 - float(discipline.get("risk_cap_adherence_rate") or 0)) / 100)))
        chase = int(discipline.get("chase_flags") or 0)
        blocked = int(discipline.get("blocked") or 0)
        slippage_gap = 1 if execution.get("applicable") and not execution.get("slippage_samples") else 0
        candidates = [
            ("weak_location", "Weak or missing location labels", missing_location, "Label location before outcome review."),
            ("undefined_risk", "Undefined stop or invalidation", missing_stop, "State entry, stop, per-unit risk, and total risk first."),
            ("risk_cap_pressure", "Risk cap pressure", risk_breaks, "Cut size until planned risk is inside the Bull Matrix."),
            ("chase_behavior", "Chase behavior", chase, "Wait for a new qualified candle instead of paying up."),
            ("guardrail_friction", "Repeated guardrail blocks", blocked, "Fix the repeated blocked reason before adding setups."),
            ("execution_measurement_gap", "Execution measurement gap", slippage_gap, "Record arrival price and fill slippage."),
        ]
        for key, label, count, correction in candidates:
            if count <= 0:
                continue
            intensity = min(100, round(count / actionable * 100)) if key != "guardrail_friction" else min(100, count * 8)
            leaks.append(
                {
                    "key": key,
                    "label": label,
                    "count": count,
                    "intensity": intensity,
                    "correction": correction,
                }
            )
        for pattern in patterns[:5]:
            if str(pattern.get("severity")) == "critical":
                leaks.append(
                    {
                        "key": pattern.get("key"),
                        "label": pattern.get("message"),
                        "count": int(pattern.get("sample") or 1),
                        "intensity": 100,
                        "correction": "Treat this as the next non-negotiable desk rule.",
                    }
                )
        leaks = sorted(leaks, key=lambda item: (int(item.get("intensity") or 0), int(item.get("count") or 0)), reverse=True)
        dominant = leaks[0] if leaks else {
            "key": "none_detected",
            "label": "No repeated mistake fingerprint is measurable yet",
            "count": 0,
            "intensity": 0,
            "correction": "Keep collecting clean journal evidence.",
        }
        return {
            "ready": bool(decisions),
            "dominant": dominant,
            "leaks": leaks[:6],
            "readback": f"{dominant['label']}: {dominant['correction']}",
        }

    def _shadow_book(self, decisions: List[dict], outcomes: List[dict], evidence: List[dict]) -> dict:
        blocked = [item for item in decisions if str(item.get("status") or "") in {"rejected", "ignored", "error"}]
        actionable = [item for item in decisions if str(item.get("status") or "") in {"proposed", "submitted"}]
        reasons = Counter(str(item.get("reason") or "unknown") for item in blocked)
        scanner_forward = []
        for item in decisions:
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            detail = metadata.get("detail") if isinstance(metadata.get("detail"), dict) else {}
            forward = item.get("forward_outcome") if isinstance(item.get("forward_outcome"), dict) else detail.get("forward_outcome") if isinstance(detail.get("forward_outcome"), dict) else {}
            if forward:
                scanner_forward.append(
                    {
                        "alert_ref": item.get("alert_ref"),
                        "symbol": item.get("symbol"),
                        "status": item.get("status"),
                        "reason": item.get("reason"),
                        "forward_outcome": forward,
                    }
                )
        saved = sum(1 for item in scanner_forward if str((item.get("forward_outcome") or {}).get("outcome") or "").lower() in {"would_stop", "stopped", "loss"})
        missed = sum(1 for item in scanner_forward if str((item.get("forward_outcome") or {}).get("outcome") or "").lower() in {"would_win", "target", "win"})
        return {
            "ready": bool(blocked or scanner_forward),
            "blocked_count": len(blocked),
            "actionable_count": len(actionable),
            "top_reasons": [{"reason": reason, "count": count} for reason, count in reasons.most_common(5)],
            "forward_replay_samples": len(scanner_forward),
            "estimated_saved_losses": saved,
            "estimated_missed_winners": missed,
            "readback": (
                f"Shadow book is tracking {len(blocked)} skipped/blocked decision(s); {len(scanner_forward)} have forward-replay evidence."
                if blocked or scanner_forward
                else "Shadow book needs skipped, rejected, or scanner-forward events before judging missed versus saved trades."
            ),
            "samples": scanner_forward[:8],
        }

    def _pre_trade_challenge(self, recommendation: dict, mode: str, decisions: List[dict]) -> dict:
        dimension = str(recommendation.get("dimension") or "process_consistency")
        questions = {
            "risk_discipline": "What is the exact invalidation, per-unit risk, and total dollar risk before this becomes real?",
            "setup_selection": "Where is this setup located relative to structure, and what would prove you are chasing?",
            "execution_quality": "What is the arrival price, participation cap, and exit plan before any order is staged?",
            "process_consistency": "Which one written rule would make you stand down from this alert?",
            "performance_quality": "Is this a process-valid setup, or are you trying to repair recent P/L?",
        }
        question = questions.get(dimension, questions["process_consistency"])
        if mode == "prop":
            question = f"Prop check: does this keep risk uniform and below the drawdown boundary? {question}"
        elif mode == "institutional":
            question = f"Institutional check: can liquidity and slippage be measured? {question}"
        return {
            "ready": True,
            "dimension": dimension,
            "question": question,
            "required_answer_shape": ["location", "invalidation", "risk", "stand-down trigger"],
            "latest_alert_ref": str((decisions[0] or {}).get("alert_ref") or "") if decisions else "",
            "advisory_only": True,
        }

    def _institutional_read(self, mode: str, decisions: List[dict], execution: dict, prop: dict) -> dict:
        plans = [item for item in decisions if isinstance(item.get("execution_plan"), dict) or isinstance(item.get("order_payload"), dict)]
        checks = [
            {
                "key": "arrival_price",
                "ok": bool(execution.get("slippage_samples")),
                "label": "Arrival-to-fill slippage is measurable",
            },
            {
                "key": "participation_cap",
                "ok": int(execution.get("participation_breaches") or 0) == 0,
                "label": "No child order exceeded participation cap",
            },
            {
                "key": "sliced_orders",
                "ok": int(execution.get("planned_slices") or 0) > 0 or mode != "institutional",
                "label": "Parent/child schedule exists when size requires it",
            },
            {
                "key": "prop_uniformity",
                "ok": mode != "prop" or not prop.get("largest_risk_increase_pct"),
                "label": "Risk size is uniform enough for prop constraints",
            },
        ]
        return {
            "applicable": mode in {"institutional", "prop"} or bool(plans),
            "mode": mode,
            "checks": checks,
            "readback": "Institutional lens is active: measure liquidity, participation, slippage, and correlated exposure before judging the setup.",
        }

    def _trade_replay_coach(self, decisions: List[dict], outcomes: List[dict]) -> dict:
        if not decisions:
            return {"ready": False, "reason": "mentor_trade_not_found"}
        decision = decisions[0]
        lesson = self._trade_lesson(decision, outcomes)
        return {
            "ready": True,
            "alert_ref": decision.get("alert_ref"),
            "symbol": decision.get("symbol"),
            "setup": decision.get("play") or decision.get("reason"),
            "markup": [
                {"label": "Setup candle", "instruction": "Compare the entry candle body, wick, and close with the playbook definition."},
                {"label": "Location", "instruction": "Mark 20/200 SMA location before looking at P/L."},
                {"label": "Invalidation", "instruction": "Verify the original stop was the structural failure point."},
            ],
            "readback": lesson,
            "advisory_only": True,
        }

    def _latest_replay_prompt(self, outcomes: List[dict]) -> dict:
        terminal = [item for item in outcomes if self._terminal(item)]
        if not terminal:
            return {
                "ready": False,
                "reason": "no_terminal_trade_yet",
                "readback": "Replay coach will unlock after a closed trade or a selected alert reference.",
            }
        item = terminal[0]
        return {
            "ready": True,
            "alert_ref": item.get("alert_ref"),
            "symbol": item.get("symbol"),
            "readback": f"Replay the latest terminal {item.get('symbol') or 'trade'} and separate entry facts from outcome.",
        }

    def _personality_payload(self, profile: dict, mode: str) -> dict:
        style = str(profile.get("coaching_style") or "leo_concise").strip().lower()
        return {
            "style": style,
            "label": style.replace("_", " ").title(),
            "persona": self.PERSONALITY_DIALS.get(style, self.PERSONALITY_DIALS["leo_concise"]),
            "mode": mode,
            "local_only": True,
        }

    def _strip_provider_fluff(self, text: str) -> str:
        fluff = (
            r"(?i)^(based on (?:your|the) current (?:velez )?(?:journal )?data,?\s*)",
            r"(?i)^(looking at (?:your|the) journal evidence,?\s*)",
            r"(?i)^(here(?:'s| is) (?:the )?(?:concise )?(?:answer|takeaway):?\s*)",
        )
        cleaned = text
        for pattern in fluff:
            cleaned = re.sub(pattern, "", cleaned).strip()
        return cleaned

    def _plain_text(self, text: str) -> str:
        cleaned = re.sub(r"[*_`#>]+", "", text)
        cleaned = re.sub(r"\s*[-•]\s+", " ", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        return cleaned.strip()

    def _trim_to_word_cap(self, text: str, cap: int) -> str:
        words = text.split()
        if len(words) <= cap:
            return text
        clipped = " ".join(words[:cap])
        sentence_end = max(clipped.rfind("."), clipped.rfind("?"), clipped.rfind("!"))
        if sentence_end >= max(40, len(clipped) * 0.55):
            return clipped[: sentence_end + 1].strip()
        return clipped.rstrip(" ,;:") + "."

    def _effective_mode(self, profile: dict) -> str:
        selected = str(profile.get("primary_mode") or "auto")
        if selected in {"retail", "institutional", "prop"}:
            return selected
        if self.risk is not None and bool(getattr(self.risk, "prop_firm_enabled", False)):
            return "prop"
        if bool(self.root_config.get("risk", {}).get("prop_firm_shield", {}).get("enabled", False)):
            return "prop"
        equity = float(
            getattr(self.risk, "last_equity", None)
            or self.root_config.get("portfolio", {}).get("initial_cash", 100000)
            or 100000
        )
        threshold = float(self.root_config.get("risk", {}).get("matrix", {}).get("institutional_threshold", 1_000_000))
        return "institutional" if equity >= threshold else "retail"

    def _discipline_metrics(self, decisions: List[dict], evidence: List[dict]) -> dict:
        relevant = [item for item in decisions if str(item.get("status") or "") != "diagnostic"]
        actionable = [item for item in relevant if str(item.get("status") or "") in {"proposed", "submitted"}]
        receipts = [item.get("confidence_receipt") for item in relevant if isinstance(item.get("confidence_receipt"), dict)]
        receipt_scores = [float(item.get("score") or 0) for item in receipts]
        for item in actionable[:5]:
            evidence.append(self._decision_evidence(item, "Actionable decision included in discipline scorecard"))
        defined_stop = sum(1 for item in actionable if self._number(item.get("stop_price")) is not None)
        defined_location = sum(1 for item in actionable if bool(item.get("location")))
        sized = sum(1 for item in actionable if int(self._number(item.get("qty")) or 0) > 0)
        risk_adherent = 0
        chased = 0
        for item in actionable:
            actual = self._estimated_risk(item)
            cap = self._number(item.get("max_dollar_risk"))
            if actual is not None and (cap is None or actual <= cap * 1.01):
                risk_adherent += 1
            receipt = item.get("confidence_receipt") or {}
            for check in receipt.get("checks", []) if isinstance(receipt, dict) else []:
                if check.get("name") == "No chase flag" and not check.get("ok"):
                    chased += 1
                    evidence.append(self._decision_evidence(item, "Chase flag recorded"))
        missing_stop = [item for item in actionable if self._number(item.get("stop_price")) is None]
        missing_location = [item for item in actionable if not item.get("location")]
        for item in missing_stop[:5]:
            evidence.append(self._decision_evidence(item, "Actionable setup had no defined stop"))
        for item in missing_location[:5]:
            evidence.append(self._decision_evidence(item, "Actionable setup lacked a location tag"))
        reasons = Counter(str(item.get("reason") or "unknown") for item in relevant if str(item.get("status") or "") in {"rejected", "ignored", "error"})
        return {
            "decisions": len(relevant),
            "actionable": len(actionable),
            "submitted": sum(1 for item in relevant if str(item.get("status") or "") == "submitted"),
            "blocked": sum(1 for item in relevant if str(item.get("status") or "") in {"rejected", "ignored", "error"}),
            "defined_stop_rate": self._rate(defined_stop, len(actionable)),
            "location_rate": self._rate(defined_location, len(actionable)),
            "sized_order_rate": self._rate(sized, len(actionable)),
            "risk_cap_adherence_rate": self._rate(risk_adherent, len(actionable)),
            "average_receipt_score": round(sum(receipt_scores) / len(receipt_scores), 1) if receipt_scores else None,
            "a_b_receipt_rate": self._rate(sum(1 for item in receipts if str(item.get("grade")) in {"A", "B"}), len(receipts)),
            "chase_flags": chased,
            "top_blocked_reasons": [{"reason": reason, "count": count} for reason, count in reasons.most_common(5)],
        }

    def _performance_metrics(self, outcomes: List[dict]) -> dict:
        terminal = [item for item in self._latest_outcome_per_trade(outcomes) if self._terminal(item)]
        r_values = [self._number(item.get("r_multiple")) for item in terminal]
        r_values = [value for value in r_values if value is not None]
        pnl_values = [self._number(item.get("pnl")) for item in terminal]
        pnl_values = [value for value in pnl_values if value is not None]
        wins = sum(1 for index, item in enumerate(terminal) if self._outcome_value(item) > 0)
        losses = sum(1 for index, item in enumerate(terminal) if self._outcome_value(item) < 0)
        gross_profit = sum(value for value in pnl_values if value > 0)
        gross_loss = abs(sum(value for value in pnl_values if value < 0))
        minimum = int(self.config.get("minimum_performance_sample", 5))
        by_setup: Dict[str, dict] = defaultdict(lambda: {"trades": 0, "wins": 0, "total_r": 0.0, "total_pnl": 0.0})
        for item in terminal:
            setup = str(item.get("setup") or item.get("play") or "unknown")
            value = self._outcome_value(item)
            by_setup[setup]["trades"] += 1
            by_setup[setup]["wins"] += 1 if value > 0 else 0
            by_setup[setup]["total_r"] += float(self._number(item.get("r_multiple")) or 0)
            by_setup[setup]["total_pnl"] += float(self._number(item.get("pnl")) or 0)
        setup_rows = []
        for setup, stats in sorted(by_setup.items(), key=lambda pair: (pair[1]["total_r"], pair[1]["total_pnl"]), reverse=True):
            setup_rows.append(
                {
                    "setup": setup,
                    "trades": stats["trades"],
                    "win_rate": self._rate(stats["wins"], stats["trades"]),
                    "expectancy_r": round(stats["total_r"] / max(1, stats["trades"]), 2),
                    "total_pnl": round(stats["total_pnl"], 2),
                }
            )
        return {
            "terminal_trades": len(terminal),
            "sufficient_sample": len(terminal) >= minimum,
            "minimum_sample": minimum,
            "wins": wins,
            "losses": losses,
            "win_rate": self._rate(wins, len(terminal)),
            "expectancy_r": round(sum(r_values) / len(r_values), 2) if r_values else None,
            "total_pnl": round(sum(pnl_values), 2),
            "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else None,
            "setups": setup_rows[:10],
        }

    def _execution_metrics(self, decisions: List[dict], outcomes: List[dict], evidence: List[dict]) -> dict:
        plans: List[tuple[dict, dict]] = []
        participation_breaches = 0
        liquidity_limited = 0
        requested = 0
        executable = 0
        planned_slices = 0
        rates: List[float] = []
        slippage: List[float] = []
        for item in decisions:
            plan = item.get("execution_plan")
            if not isinstance(plan, dict):
                payload = item.get("order_payload") if isinstance(item.get("order_payload"), dict) else {}
                plan = payload.get("_bullpilot_execution_plan")
            if not isinstance(plan, dict) or not plan:
                fill_bps = self._slippage_bps(item)
                if fill_bps is not None:
                    slippage.append(fill_bps)
                continue
            plans.append((item, plan))
            requested += int(self._number(plan.get("requested_qty")) or item.get("qty") or 0)
            executable += int(self._number(plan.get("executable_qty")) or item.get("qty") or 0)
            liquidity_limited += 1 if plan.get("liquidity_limited") else 0
            rates.append(float(self._number(plan.get("participation_rate")) or 0))
            slices = plan.get("slices") if isinstance(plan.get("slices"), list) else []
            planned_slices += len(slices)
            for child in slices:
                qty = int(self._number(child.get("qty")) or 0)
                cap = int(self._number(child.get("participation_cap_qty")) or 0)
                if cap > 0 and qty > cap:
                    participation_breaches += 1
                    evidence.append(self._decision_evidence(item, f"Child slice {qty} exceeded cap {cap}"))
            fill_bps = self._slippage_bps(item)
            if fill_bps is not None:
                slippage.append(fill_bps)
        return {
            "applicable": bool(plans),
            "planned_parents": len(plans),
            "planned_slices": planned_slices,
            "requested_qty": requested,
            "executable_qty": executable,
            "planned_fill_ratio": round(executable / requested * 100, 1) if requested > 0 else None,
            "liquidity_limited_parents": liquidity_limited,
            "average_participation_rate": round(sum(rates) / len(rates) * 100, 2) if rates else None,
            "maximum_participation_rate": round(max(rates) * 100, 2) if rates else None,
            "participation_breaches": participation_breaches,
            "slippage_samples": len(slippage),
            "average_slippage_bps": round(sum(slippage) / len(slippage), 2) if slippage else None,
        }

    def _prop_metrics(self, decisions: List[dict], outcomes: List[dict], evidence: List[dict]) -> dict:
        actionable = [item for item in decisions if str(item.get("status") or "") in {"proposed", "submitted"}]
        risk_values = [self._estimated_risk(item) for item in sorted(actionable, key=lambda row: str(row.get("timestamp") or ""))]
        risk_values = [value for value in risk_values if value is not None and value > 0]
        increases = [
            (risk_values[index] - risk_values[index - 1]) / risk_values[index - 1] * 100
            for index in range(1, len(risk_values))
            if risk_values[index - 1] > 0
        ]
        average = sum(risk_values) / len(risk_values) if risk_values else 0.0
        variance = sum((value - average) ** 2 for value in risk_values) / len(risk_values) if risk_values else 0.0
        cv = math.sqrt(variance) / average * 100 if average > 0 else None
        prop_reasons = Counter(
            str(item.get("reason") or "")
            for item in decisions
            if any(token in str(item.get("reason") or "").lower() for token in ("prop_", "daily_loss", "news_blackout", "consistency", "drawdown"))
        )
        for item in decisions:
            reason = str(item.get("reason") or "").lower()
            if any(token in reason for token in ("prop_", "daily_loss", "news_blackout", "consistency", "drawdown")):
                evidence.append(self._decision_evidence(item, f"Prop guardrail: {reason}"))
        snapshot = {}
        if self.risk is not None and callable(getattr(self.risk, "state_snapshot", None)):
            equity = float(
                getattr(self.risk, "last_equity", None)
                or self.root_config.get("portfolio", {}).get("initial_cash", 100000)
                or 100000
            )
            snapshot = self.risk.state_snapshot(equity)
        profile = snapshot.get("profile") or {}
        daily_loss_limit = self._number(profile.get("max_daily_loss_dollars"))
        account_daily_pnl = self._number(snapshot.get("account_daily_pnl"))
        utilization = abs(min(0.0, account_daily_pnl or 0.0)) / daily_loss_limit * 100 if daily_loss_limit else None
        return {
            "applicable": True,
            "planned_risk_samples": len(risk_values),
            "average_planned_risk": round(average, 2) if risk_values else None,
            "risk_size_coefficient_of_variation": round(cv, 2) if cv is not None else None,
            "largest_risk_increase_pct": round(max(increases), 2) if increases else None,
            "daily_loss_utilization_pct": round(utilization, 2) if utilization is not None else None,
            "guardrail_events": [{"reason": reason, "count": count} for reason, count in prop_reasons.most_common()],
            "profit_lock_active": any(reason in prop_reasons for reason in ("prop_profit_lock", "prop_consistency_cap")),
            "risk_state": snapshot,
        }

    def _scorecards(
        self,
        *,
        decisions: List[dict],
        discipline: dict,
        performance: dict,
        execution: dict,
        prop: dict,
        mode: str,
    ) -> List[dict]:
        decision_count = int(discipline.get("decisions") or 0)
        actionable = int(discipline.get("actionable") or 0)
        risk_score = None
        setup_score = None
        process_score = None
        if actionable:
            risk_score = round(
                0.55 * discipline["risk_cap_adherence_rate"]
                + 0.35 * discipline["defined_stop_rate"]
                + 0.10 * discipline["sized_order_rate"]
            )
            setup_score = round(
                0.55 * discipline["location_rate"]
                + 0.35 * float(discipline.get("average_receipt_score") or 0)
                + 0.10 * max(0.0, 100.0 - discipline.get("chase_flags", 0) / actionable * 100)
            )
        if decision_count:
            duplicate_count = next(
                (row["count"] for row in discipline.get("top_blocked_reasons", []) if row["reason"] == "duplicate_alert"),
                0,
            )
            process_score = round(max(0.0, 100.0 - duplicate_count / decision_count * 30.0))

        execution_score = None
        if execution.get("applicable"):
            execution_score = 100
            execution_score -= min(60, int(execution.get("participation_breaches") or 0) * 20)
            average_slippage = execution.get("average_slippage_bps")
            if average_slippage is not None and average_slippage > float(self.config.get("slippage_warning_bps", 10)):
                execution_score -= min(30, round(average_slippage))
            execution_score = max(0, execution_score)
        elif actionable and mode == "retail":
            execution_score = round((discipline["defined_stop_rate"] + discipline["sized_order_rate"]) / 2)

        if mode == "prop" and prop.get("planned_risk_samples"):
            cv = prop.get("risk_size_coefficient_of_variation")
            uniformity_score = max(0, round(100 - float(cv or 0) * 2))
            process_score = round((float(process_score or 0) + uniformity_score) / 2)

        rows = [
            self._scorecard("risk_discipline", "Risk discipline", risk_score, actionable, "Defined stops, sizing, and Bull Matrix cap adherence."),
            self._scorecard("setup_selection", "Setup selection", setup_score, actionable, "Location quality, confidence receipts, and chase control."),
            self._scorecard("execution_quality", "Execution quality", execution_score, execution.get("planned_parents") or actionable, "Schedule, participation, protection, and measurable slippage."),
            self._scorecard("process_consistency", "Process consistency", process_score, decision_count, "Repeatable alert handling, reviews, and prop-size uniformity."),
        ]
        if performance.get("sufficient_sample"):
            expectancy = self._number(performance.get("expectancy_r")) or 0
            performance_score = max(0, min(100, round(50 + expectancy * 25)))
        else:
            performance_score = None
        rows.append(
            self._scorecard(
                "performance_quality",
                "Performance quality",
                performance_score,
                performance.get("terminal_trades", 0),
                "Closed-trade expectancy and profit factor; hidden until the minimum sample is met.",
            )
        )
        return rows

    def _patterns(
        self,
        decisions: List[dict],
        discipline: dict,
        performance: dict,
        execution: dict,
        prop: dict,
        mode: str,
        evidence: List[dict],
    ) -> List[dict]:
        patterns: List[dict] = []
        actionable = int(discipline.get("actionable") or 0)
        if actionable and discipline.get("defined_stop_rate", 100) < 100:
            patterns.append(self._pattern("critical", "undefined_risk", "Some actionable setups lacked a defined stop.", actionable))
        if actionable >= 3 and discipline.get("location_rate", 100) < 80:
            patterns.append(self._pattern("warning", "weak_location_discipline", "Location tags are missing too often for reliable playbook review.", actionable))
        if discipline.get("chase_flags", 0):
            patterns.append(self._pattern("warning", "chase_behavior", f"{discipline['chase_flags']} actionable setup(s) carried a chase flag.", discipline["chase_flags"]))
        if execution.get("participation_breaches", 0):
            patterns.append(self._pattern("critical", "participation_breach", "At least one institutional child exceeded its planned participation cap.", execution["participation_breaches"]))
        if execution.get("slippage_samples", 0) == 0 and mode == "institutional":
            patterns.append(self._pattern("info", "execution_measurement_gap", "No arrival-to-fill slippage sample is available yet.", 0))
        if mode == "prop":
            max_increase = prop.get("largest_risk_increase_pct")
            allowed = float(self.root_config.get("risk", {}).get("prop_firm_shield", {}).get("max_risk_increase_pct", 10))
            if max_increase is not None and max_increase > allowed:
                patterns.append(self._pattern("critical", "risk_size_escalation", f"Planned risk increased {max_increase:.1f}%, above the {allowed:.1f}% uniformity limit.", prop.get("planned_risk_samples", 0)))
        if not performance.get("sufficient_sample"):
            patterns.append(
                self._pattern(
                    "info",
                    "performance_sample_low",
                    f"Expectancy is withheld until {performance.get('minimum_sample', 5)} terminal outcomes exist.",
                    performance.get("terminal_trades", 0),
                )
            )
        top_reason = (discipline.get("top_blocked_reasons") or [{}])[0]
        if top_reason.get("count", 0) >= 3 and top_reason.get("reason") not in {"duplicate_alert", "outside_session"}:
            patterns.append(
                self._pattern(
                    "warning",
                    "repeated_guardrail",
                    f"The most repeated blocked reason is {top_reason.get('reason')} ({top_reason.get('count')} times).",
                    top_reason.get("count", 0),
                )
            )
        return patterns[:8]

    def _recommendation(self, scorecards: List[dict], patterns: List[dict], mode: str) -> dict:
        critical = next((item for item in patterns if item.get("severity") == "critical"), None)
        scored = [item for item in scorecards if item.get("score") is not None]
        weakest = min(scored, key=lambda item: item["score"]) if scored else None
        dimension = str((weakest or {}).get("key") or "process_consistency")
        if critical and critical.get("key") in {"undefined_risk", "risk_size_escalation"}:
            dimension = "risk_discipline"
        elif critical and critical.get("key") == "participation_breach":
            dimension = "execution_quality"

        recommendations = {
            "risk_discipline": {
                "title": "Five-trade risk rehearsal",
                "instruction": "Before the next five proposals, state entry, invalidation, risk per unit, total risk, and Bull Matrix cap. Do not count a trade unless all five agree.",
            },
            "setup_selection": {
                "title": "Location-first replay",
                "instruction": "Replay five recent alerts and label structural location before looking at the result. Keep only setups whose location and no-chase checks pass.",
            },
            "execution_quality": {
                "title": "Execution receipt audit",
                "instruction": "Review the next three parent orders for arrival price, participation cap, child schedule, fill ratio, and slippage. Record missing measurements as gaps.",
            },
            "process_consistency": {
                "title": "One-rule session",
                "instruction": "Choose one written process rule before the session, follow it on every alert, and acknowledge the drill only after the close review.",
            },
            "performance_quality": {
                "title": "Outcome-quality sample",
                "instruction": "Close and reconcile enough paper trades to reach the minimum sample. Judge the process now; judge expectancy only after the sample threshold.",
            },
        }
        selected = dict(recommendations.get(dimension, recommendations["process_consistency"]))
        selected["dimension"] = dimension
        selected["mode"] = mode
        selected["why"] = (
            critical.get("message")
            if critical
            else f"{(weakest or {}).get('label', 'Process consistency')} is the lowest currently measurable coaching dimension."
        )
        return selected

    def _persist_drill(self, recommendation: dict, evidence: List[dict], period: dict) -> dict:
        fingerprint = self._fingerprint(
            {
                "period": str(period.get("start") or "")[:10],
                "dimension": recommendation.get("dimension"),
                "title": recommendation.get("title"),
            }
        )
        return self.journal.upsert_mentor_drill(
            {
                "fingerprint": fingerprint,
                "title": recommendation.get("title"),
                "instruction": recommendation.get("instruction"),
                "dimension": recommendation.get("dimension"),
                "evidence": self._dedupe_evidence(evidence)[:6],
            }
        )

    def _sample_assessment(self, decisions: List[dict], performance: dict, execution: dict) -> dict:
        terminal = int(performance.get("terminal_trades") or 0)
        minimum = int(performance.get("minimum_sample") or 5)
        performance_confidence = "high" if terminal >= 20 else "medium" if terminal >= minimum else "insufficient"
        return {
            "decisions": {
                "count": len(decisions),
                "confidence": "high" if len(decisions) >= 20 else "medium" if len(decisions) >= 5 else "low",
                "note": "Discipline scores describe observed journal decisions, not profitability.",
            },
            "performance": {
                "count": terminal,
                "confidence": performance_confidence,
                "note": (
                    "Closed-trade performance is statistically thin; expectancy conclusions are withheld."
                    if terminal < minimum
                    else "Performance metrics meet the configured minimum sample, but remain historical rather than predictive."
                ),
            },
            "execution": {
                "count": int(execution.get("slippage_samples") or 0),
                "confidence": "medium" if int(execution.get("slippage_samples") or 0) >= 5 else "low",
                "note": "Execution conclusions require broker fill prices and an arrival-price reference.",
            },
        }

    def _headline(self, scorecards: List[dict], recommendation: dict, sample: dict, scope: str) -> str:
        measurable = [item for item in scorecards if item.get("score") is not None]
        if not measurable:
            return f"Velez Mentor needs more {scope} journal evidence. Start with {recommendation.get('title', 'one disciplined review')}."
        best = max(measurable, key=lambda item: item["score"])
        weakest = min(measurable, key=lambda item: item["score"])
        return (
            f"{best['label']} leads at {best['score']}/100; {weakest['label'].lower()} is the current development edge "
            f"at {weakest['score']}/100. Focus: {recommendation.get('title')}."
        )

    def _trade_detail(self, decisions: List[dict], outcomes: List[dict]) -> dict:
        if not decisions:
            return {"found": False, "reason": "mentor_trade_not_found"}
        decision = decisions[0]
        receipt = decision.get("confidence_receipt") if isinstance(decision.get("confidence_receipt"), dict) else {}
        return {
            "found": True,
            "alert_ref": decision.get("alert_ref"),
            "symbol": decision.get("symbol"),
            "setup": decision.get("play") or decision.get("reason"),
            "status": decision.get("status"),
            "reason": decision.get("reason"),
            "receipt": receipt,
            "estimated_risk": self._estimated_risk(decision),
            "outcomes": outcomes,
            "lesson": self._trade_lesson(decision, outcomes),
        }

    def _trade_lesson(self, decision: dict, outcomes: List[dict]) -> str:
        if self._number(decision.get("stop_price")) is None:
            return "The first correction is a defined invalidation level; outcome analysis is secondary when risk was undefined."
        if not decision.get("location"):
            return "The setup needs a structural location label before its result can teach a repeatable playbook lesson."
        terminal = [item for item in outcomes if self._terminal(item)]
        if not terminal:
            return "The setup receipt is reviewable, but no terminal outcome is linked yet. Do not infer success from an open-position milestone."
        value = self._outcome_value(terminal[0])
        return (
            "The trade finished positive; preserve the process checks and compare exit efficiency."
            if value > 0
            else "The trade finished negative; distinguish a valid planned loss from a process violation before changing the setup."
        )

    def _persist_report_once(self, report: dict) -> int:
        recent = self.journal.latest_mentor_reports(limit=20)
        existing = next(
            (
                item
                for item in recent
                if item.get("scope") == report.get("scope")
                and item.get("report_fingerprint") == report.get("report_fingerprint")
            ),
            None,
        )
        if existing:
            return int(existing.get("id") or 0)
        return self.journal.save_mentor_report(report)

    def _scorecard(self, key: str, label: str, score: Optional[float], sample: int, explanation: str) -> dict:
        return {
            "key": key,
            "label": label,
            "score": None if score is None else max(0, min(100, int(round(score)))),
            "sample": int(sample or 0),
            "status": "insufficient" if score is None else "strong" if score >= 85 else "developing" if score >= 65 else "focus",
            "explanation": explanation,
        }

    def _score_text(self, report: dict, key: str) -> str:
        item = next((row for row in report.get("scorecards", []) if row.get("key") == key), {})
        return "not yet measurable" if item.get("score") is None else f"{item['score']}/100"

    def _pattern(self, severity: str, key: str, message: str, sample: int) -> dict:
        return {"severity": severity, "key": key, "message": message, "sample": int(sample or 0)}

    def _decision_evidence(self, item: dict, label: str) -> dict:
        return {
            "source": "journal_decision",
            "journal_id": item.get("journal_id"),
            "alert_ref": item.get("alert_ref"),
            "timestamp": item.get("timestamp"),
            "symbol": item.get("symbol"),
            "label": label,
        }

    def _dedupe_evidence(self, evidence: Iterable[dict]) -> List[dict]:
        seen = set()
        result = []
        for item in evidence:
            key = (item.get("source"), item.get("journal_id"), item.get("alert_ref"), item.get("label"))
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    def _latest_outcome_per_trade(self, outcomes: List[dict]) -> List[dict]:
        latest: Dict[str, dict] = {}
        for item in outcomes:
            ref = str(item.get("alert_ref") or f"outcome-{item.get('id')}")
            if ref not in latest:
                latest[ref] = item
            elif self._terminal(item) and not self._terminal(latest[ref]):
                latest[ref] = item
        return list(latest.values())

    def _terminal(self, outcome: dict) -> bool:
        status = str(outcome.get("status") or "").strip().lower()
        return bool(outcome.get("terminal")) or status in self.TERMINAL_STATUSES or status.startswith("closed_")

    def _outcome_value(self, outcome: dict) -> float:
        r_value = self._number(outcome.get("r_multiple"))
        if r_value is not None:
            return r_value
        pnl = self._number(outcome.get("pnl"))
        if pnl is not None:
            return pnl
        status = str(outcome.get("status") or "").lower()
        if status in {"won", "target_hit", "take_profit"}:
            return 1.0
        if status in {"lost", "stopped_out", "stop_loss"}:
            return -1.0
        return 0.0

    def _estimated_risk(self, item: dict) -> Optional[float]:
        entry = self._number(item.get("entry_price"))
        stop = self._number(item.get("stop_price"))
        qty = self._number(item.get("qty"))
        if entry is None or stop is None or qty is None or qty <= 0:
            return None
        multiplier = self._number(item.get("contract_multiplier")) or 1.0
        return round(abs(entry - stop) * qty * multiplier, 2)

    def _slippage_bps(self, item: dict) -> Optional[float]:
        arrival = self._number(item.get("entry_price"))
        response = item.get("broker_response") if isinstance(item.get("broker_response"), dict) else {}
        fill = None
        for key in ("filled_avg_price", "average_fill_price", "fill_price", "avg_fill_price"):
            fill = self._number(response.get(key))
            if fill is not None:
                break
        if arrival is None or arrival <= 0 or fill is None:
            return None
        direction = 1.0 if str(item.get("side") or "").lower() in {"buy", "long"} else -1.0
        return round((fill - arrival) / arrival * 10000 * direction, 2)

    def _rate(self, numerator: int, denominator: int) -> float:
        return round(float(numerator) / max(1, int(denominator)) * 100.0, 1) if denominator else 0.0

    def _number(self, value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    def _aware_now(self, value: Optional[datetime]) -> datetime:
        current = value or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=self.trading_timezone)
        return current

    def _fingerprint(self, value: Any) -> str:
        payload = json.dumps(value, default=str, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
