from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("PropManager")


class PropProfileManager:
    """Dynamic Prop Firm Profile Manager.
    Loads prop firm rules (Apex, Topstep, Take Profit Trader, Lucid, FTMO, Earn2Trade, Bulenox)
    and re-calibrates RiskManager & Broker rules dynamically at runtime or startup.
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
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load prop_profiles.json: {e}")
        return {}

    def _get_initial_profile_key(self) -> str:
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
            "firm": "Apex Trader Funding",
            "name": "Apex 50K",
            "account_size": 50000,
            "max_trailing_drawdown": 2500.0,
            "drawdown_type": "intraday_trailing",
            "profit_target": 3000.0,
            "max_contracts": 10,
            "eod_flatten_time_et": "15:55",
            "consistency_profit_cap_pct": 30.0
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

        if risk_manager:
            self.apply_to_risk_manager(risk_manager, profile)

        if broker and hasattr(broker, "config"):
            self.apply_to_broker(broker, profile)

        return profile

    def apply_to_risk_manager(self, risk_manager: Any, profile: Optional[dict] = None) -> None:
        p = profile or self.get_active_profile()
        if hasattr(risk_manager, "prop_config"):
            risk_manager.prop_config["max_trailing_drawdown"] = p.get("max_trailing_drawdown", 2500.0)
            risk_manager.prop_config["drawdown_type"] = p.get("drawdown_type", "intraday_trailing")
            risk_manager.prop_config["max_open_positions"] = p.get("max_contracts", 10)
            risk_manager.prop_config["profit_target_dollars"] = p.get("profit_target", 3000.0)
            if "daily_loss_limit" in p:
                risk_manager.prop_config["max_daily_loss_dollars"] = p["daily_loss_limit"]

    def apply_to_broker(self, broker: Any, profile: Optional[dict] = None) -> None:
        p = profile or self.get_active_profile()
        cfg = getattr(broker, "config", None)
        if cfg:
            object.__setattr__(cfg, "max_trailing_drawdown", float(p.get("max_trailing_drawdown", 2500.0))) if hasattr(cfg, "max_trailing_drawdown") else None
            object.__setattr__(cfg, "eod_flatten_time_et", str(p.get("eod_flatten_time_et", "15:55"))) if hasattr(cfg, "eod_flatten_time_et") else None
            if "daily_profit_cap" in p and hasattr(cfg, "daily_profit_cap"):
                object.__setattr__(cfg, "daily_profit_cap", float(p["daily_profit_cap"]))
