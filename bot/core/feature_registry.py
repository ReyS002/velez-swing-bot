"""Server-side Trading Bull Desk feature and entitlement registry.

Billing is intentionally absent.  The registry is the stable contract a future
billing service can map to, while the existing authenticated owner defaults to
full access.  Safety and account-state features are always Core.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional


FEATURE_REGISTRY: Dict[str, Dict[str, Any]] = {
    "desk": {"tier": "core", "label": "Desk", "safety": False},
    "tradingview_trade": {"tier": "core", "label": "TradingView Trade workspace", "safety": False},
    "setup_market_context": {"tier": "core", "label": "Setup and market context", "safety": False},
    "essential_risk": {"tier": "core", "label": "Risk warnings and limits", "safety": True},
    "basic_planner": {"tier": "core", "label": "Execution planning", "safety": True},
    "basic_journal": {"tier": "core", "label": "Trade journal", "safety": False},
    "health_auth_safety": {"tier": "core", "label": "Health, authentication, approvals, and emergency state", "safety": True},
    "playbook": {"tier": "core", "label": "Velez playbook", "safety": False},
    "thesis_notes": {"tier": "core", "label": "Private ticker thesis notes", "safety": False},
    "basic_annotations": {"tier": "core", "label": "Verified plan levels", "safety": True},
    "pro_console": {"tier": "pro", "label": "Pro Console", "safety": False},
    "advanced_readiness": {"tier": "pro", "label": "Advanced readiness breakdown", "safety": False},
    "planner_analytics": {"tier": "pro", "label": "Advanced planner analytics", "safety": False},
    "performance_attribution": {"tier": "pro", "label": "Performance attribution", "safety": False},
    "coach_intelligence": {"tier": "pro", "label": "Mentor and Coach intelligence", "safety": False},
    "missed_trade_analysis": {"tier": "pro", "label": "Missed-trade analysis", "safety": False},
    "discipline_score": {"tier": "pro", "label": "Trader Discipline Score", "safety": False},
    "replay_lab": {"tier": "pro", "label": "Replay and Lab", "safety": False},
    "advanced_annotations": {"tier": "pro", "label": "Advanced chart annotations", "safety": False},
    "deep_regime_analytics": {"tier": "pro", "label": "Deep regime and strategy analytics", "safety": False},
}


TIER_ORDER = {"core": 0, "pro": 1}


def dashboard_tier(username: str = "") -> str:
    """Return the authenticated dashboard tier without consulting billing.

    The current owner/admin experience remains Pro by default.  A future
    billing integration may set ``VELEZ_DASHBOARD_TIER=core`` for a non-admin
    account.  Explicit admin usernames always retain Pro access.
    """

    cleaned_username = str(username or "").strip().lower()
    admins = {
        item.strip().lower()
        for item in os.getenv("VELEZ_DASHBOARD_ADMIN_USERS", "").split(",")
        if item.strip()
    }
    if cleaned_username and cleaned_username in admins:
        return "pro"
    configured = os.getenv("VELEZ_DASHBOARD_TIER", "pro").strip().lower()
    return configured if configured in TIER_ORDER else "pro"


def feature_allowed(feature: str, tier: Optional[str] = None) -> bool:
    definition = FEATURE_REGISTRY.get(str(feature or "").strip())
    if definition is None:
        return False
    if definition.get("safety"):
        return True
    resolved = str(tier or dashboard_tier()).strip().lower()
    if resolved not in TIER_ORDER:
        return False
    required = str(definition.get("tier") or "pro")
    return TIER_ORDER[resolved] >= TIER_ORDER.get(required, 1)


def entitlement_payload(tier: Optional[str] = None) -> dict:
    resolved = str(tier or dashboard_tier()).strip().lower()
    if resolved not in TIER_ORDER:
        resolved = "core"
    features = {
        key: {
            "allowed": feature_allowed(key, resolved),
            "tier": value["tier"],
            "label": value["label"],
            "safety": bool(value.get("safety")),
        }
        for key, value in FEATURE_REGISTRY.items()
    }
    return {
        "ok": True,
        "tier": resolved,
        "features": features,
        "billing_connected": False,
        "owner_default_full_access": True,
        "guardrail": "Safety, risk, endpoint, approval, health, and emergency state are never premium-only.",
    }


def premium_feature_for_path(path: str) -> Optional[str]:
    """Map protected API paths to their server-enforced premium feature."""

    cleaned = str(path or "")
    safety_mentor_paths = {
        "/api/mentor/guardrail-do-not-touch",
        "/api/mentor/broker-reconciliation",
        "/api/mentor/cross-bot-risk",
    }
    if cleaned in safety_mentor_paths:
        return None
    if cleaned.startswith("/api/mentor/"):
        return "coach_intelligence"
    if cleaned.startswith("/api/replay/"):
        return "replay_lab"
    if cleaned.startswith("/api/analytics/") or cleaned == "/api/journal/intelligence":
        return "performance_attribution"
    if cleaned.startswith("/api/missed-trades"):
        return "missed_trade_analysis"
    if cleaned.startswith("/api/discipline"):
        return "discipline_score"
    if cleaned.startswith("/api/pro/"):
        return "pro_console"
    return None
