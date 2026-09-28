"""Client for BullWarden's independent prop-account entry gate.

The client only guards *new entries*.  It never blocks an exit, a protective
stop placement, or a stop repair, so an unavailable safety service cannot make
an open position less safe.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any

import requests


def _enabled(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class BullWardenClient:
    def __init__(self) -> None:
        self.enabled = _enabled("BULLWARDEN_ENABLED", False)
        self.fail_closed = _enabled("BULLWARDEN_FAIL_CLOSED", True)
        self.url = os.getenv("BULLWARDEN_URL", "http://bull-warden:8090").rstrip("/")
        self.api_key = os.getenv("BULLWARDEN_API_KEY", "").strip()
        self.account_id = os.getenv("BULLWARDEN_ACCOUNT_ID", "").strip()
        self.timeout_seconds = max(0.2, min(float(os.getenv("BULLWARDEN_TIMEOUT_SECONDS", "2")), 10.0))

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def status(self) -> dict[str, Any]:
        missing = [name for name, value in (("BULLWARDEN_API_KEY", self.api_key), ("BULLWARDEN_ACCOUNT_ID", self.account_id)) if not value]
        return {"enabled": self.enabled, "ready": self.enabled and not missing, "fail_closed": self.fail_closed, "missing": missing, "url": self.url}

    def entry_allowed(
        self,
        broker: Any,
        *,
        source: str,
        order_ref: str = "",
        trade: dict[str, Any] | None = None,
        commit_intent: bool = True,
    ) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": True, "allowed": True, "active": False, "reason": "bullwarden_disabled"}
        if not self.api_key or not self.account_id:
            return self._failure("bullwarden_not_configured")
        try:
            account = broker.get_account()
            equity = self._number(account.get("equity") or account.get("portfolio_value") or account.get("cash"))
            prior_close = self._number(account.get("last_equity"))
            if equity is None or equity <= 0:
                return self._failure("bullwarden_equity_unavailable")
            control = dict(trade or {})
            intent_id = str(order_ref or control.get("signal_id") or "")
            if len(intent_id) < 8:
                intent_id = "intent-" + sha256(intent_id.encode("utf-8")).hexdigest()[:24] if intent_id else ""
            if not intent_id:
                return self._failure("bullwarden_intent_id_missing")
            fingerprint = sha256(
                json.dumps({"intent_id": intent_id, "trade": control}, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
            ).hexdigest()
            response = requests.post(
                f"{self.url}/v1/prop/evaluate",
                headers={"X-BullWarden-Key": self.api_key},
                json={
                    "schema_version": "bullwarden.prop-trade.v1",
                    "account_id": self.account_id, "intent_id": intent_id,
                    "intent_fingerprint": fingerprint, "asset_class": control.get("asset_class", "stocks"),
                    "mode": control.get("mode", "paper"), "equity": equity,
                    "prior_close_equity": prior_close, "source": source,
                    "account_observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "commit_intent": commit_intent,
                    **control,
                },
                timeout=self.timeout_seconds,
            )
            if response.status_code != 200:
                return self._failure(f"bullwarden_http_{response.status_code}")
            body = response.json()
            if not isinstance(body, dict) or not isinstance(body.get("submit_eligible"), bool):
                return self._failure("bullwarden_invalid_response")
            return {
                "ok": bool(body.get("ok", True)), "allowed": bool(body["submit_eligible"]),
                "submit_eligible": bool(body["submit_eligible"]), "active": True,
                "reason": str(body.get("reason") or "unknown"),
                "review_action_label": str(body.get("review_action_label") or "Conditions Not Met"),
                "result": body,
            }
        except Exception as exc:
            return self._failure(f"bullwarden_unavailable:{type(exc).__name__}")

    def _failure(self, reason: str) -> dict[str, Any]:
        return {"ok": False, "allowed": not self.fail_closed, "active": True, "reason": reason}
