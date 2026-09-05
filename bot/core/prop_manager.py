from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("PropManager")


class PropProfileManager:
    """Legacy profile catalogue for display and migration only.

    BullWarden is the sole rule authority. Values in this file are explicitly
    unverified and can never recalibrate execution or broker controls.
    """

    def __init__(self, journal_store: Optional[Any] = None) -> None:
        self.journal = journal_store
        self.profiles: Dict[str, dict] = self._load_profiles()
        self.active_profile_key: str = self._get_initial_profile_key()

    def _load_profiles(self) -> Dict[str, dict]:
        json_path = Path(__file__).parent / "prop_profiles.json"
        if json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    legacy = json.load(f)
                    return {
                        key: {**value, "profile_key": key, "rules_version": "legacy-import-1", "status": "review_required", "submit_eligible": False, "canonical_authority": "BullWarden"}
                        for key, value in legacy.items()
                    }
            except Exception as e:
                logger.error(f"Failed to load prop_profiles.json: {e}")
        return {}

    def _get_initial_profile_key(self) -> str:
        # Check SQLite journal setting first, then env, default to apex_50k
        if self.journal:
            saved = self.journal.get_setting("active_prop_profile", None)
            if saved and saved in self.profiles:
                return str(saved)
        env_profile = os.getenv("PROP_PROFILE", "apex_50k").lower().strip()
        if env_profile in self.profiles:
            return env_profile
        return "apex_50k"

    def get_active_profile(self) -> dict:
        return self.profiles.get(self.active_profile_key, {
            "profile_key": self.active_profile_key, "status": "disabled",
            "submit_eligible": False, "canonical_authority": "BullWarden",
        })

    def list_profiles(self) -> Dict[str, dict]:
        return self.profiles

    def select_profile(self, profile_key: str, risk_manager: Optional[Any] = None, broker: Optional[Any] = None) -> dict:
        key = profile_key.lower().strip()
        if key not in self.profiles:
            raise ValueError(f"Unknown prop profile '{key}'. Available: {list(self.profiles.keys())}")

        self.active_profile_key = key
        if self.journal:
            self.journal.set_setting("active_prop_profile", key)

        profile = self.get_active_profile()
        logger.info(f"Switched active prop firm profile to: {profile.get('name')} ({key})")

        if risk_manager or broker:
            logger.warning("Legacy profile selected for display only; BullWarden remains authoritative")

        return profile

    def apply_to_risk_manager(self, risk_manager: Any, profile: Optional[dict] = None) -> None:
        logger.info("Skipped legacy profile risk calibration; BullWarden is authoritative")

    def apply_to_broker(self, broker: Any, profile: Optional[dict] = None) -> None:
        logger.info("Skipped legacy profile broker calibration; BullWarden is authoritative")
