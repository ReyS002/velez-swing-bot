from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional


POWER_PLAYS = {
    "elephant_bar",
    "bull_180",
    "bear_180",
    "bottoming_tail",
    "topping_tail",
    "opening_gap_go",
    "time_space_breakout",
}

CONTRARIAN_REVERSAL_PLAYS = {
    "bottoming_tail",
    "topping_tail",
    "failed_new_high",
    "failed_new_low",
    "opening_gap_fade",
}

DEFAULT_LOT_SIZING_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "max_lots": 4,
    "lot_risk_fraction": 0.25,
    "default_lots": 1,
    "setup_base_lots": {
        "elephant_bar": 2,
        "bull_180": 2,
        "bear_180": 2,
        "bottoming_tail": 2,
        "topping_tail": 2,
        "opening_gap_go": 2,
        "time_space_breakout": 2,
        "opening_gap_fade": 1,
        "velez_buy_setup": 1,
        "velez_sell_setup": 1,
        "nrb_acorn": 1,
        "fab4_trap_breakout": 1,
        "failed_new_high": 1,
        "failed_new_low": 1,
    },
    "near_20_power_bonus_lots": 1,
    "near_200_bonus_lots": 1,
    "power_candle_bonus_lots": 1,
    "high_quality_open_bonus_lots": 1,
    "power_body_mult": 2.3,
    "power_tail_pct": 0.75,
    "power_recovery_pct": 0.95,
    "high_quality_time_space_score": 0.8,
    "missing_location_cap_lots": 1,
    "chased_cap_lots": 2,
    "extended_continuation_cap_lots": 1,
    "wide_stop_cap_lots": 2,
    "wide_stop_pct_of_max": 0.5,
    "allow_alert_lot_override": False,
}


def merged_lot_sizing_config(config: Optional[dict]) -> dict:
    merged = deepcopy(DEFAULT_LOT_SIZING_CONFIG)
    for key, value in (config or {}).items():
        if key == "setup_base_lots" and isinstance(value, dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def build_lot_plan(
    *,
    play: str,
    metadata: dict,
    entry_price: float,
    stop_price: float,
    max_risk_budget: float,
    max_stop_pct: float,
    config: Optional[dict] = None,
) -> dict:
    cfg = merged_lot_sizing_config(config)
    max_lots = max(1, int(_number(cfg.get("max_lots"), 4) or 4))
    lot_fraction = max(0.01, min(_number(cfg.get("lot_risk_fraction"), 0.25) or 0.25, 1.0))
    if not bool(cfg.get("enabled", True)):
        lots = max_lots
        return _plan(
            lots=lots,
            max_lots=max_lots,
            lot_fraction=lot_fraction,
            max_risk_budget=max_risk_budget,
            factors=["lot_sizing_disabled_full_risk"],
            caps=[],
            label=f"{lots}/{max_lots} lots",
        )

    normalized_play = str(play or "").strip().lower()
    base_lots = int(_number(cfg.get("setup_base_lots", {}).get(normalized_play), cfg.get("default_lots", 1)) or 1)
    lots = base_lots
    factors = [f"base_{normalized_play or 'setup'}_{base_lots}_lot"]
    caps: List[str] = []

    locations = normalize_locations(metadata.get("location"))
    near20 = any("location_1" in item or "near_20" in item for item in locations)
    extended20 = any("location_2" in item or "extended" in item for item in locations)
    near200 = any("location_3" in item or "near_200" in item for item in locations)

    if near200:
        bonus = int(_number(cfg.get("near_200_bonus_lots"), 1) or 0)
        lots += bonus
        factors.append(f"near_200_power_bonus_+{bonus}")
    elif near20 and normalized_play in POWER_PLAYS:
        bonus = int(_number(cfg.get("near_20_power_bonus_lots"), 1) or 0)
        lots += bonus
        factors.append(f"near_20_power_bonus_+{bonus}")

    body_mult = _first_number(metadata, "body_mult", "event_candle_body_mult")
    if body_mult is not None and body_mult >= float(cfg.get("power_body_mult", 2.3)):
        bonus = int(_number(cfg.get("power_candle_bonus_lots"), 1) or 0)
        lots += bonus
        factors.append(f"power_body_{body_mult:.2f}x_+{bonus}")

    tail_pct = _first_number(metadata, "tail_pct", "event_tail_pct")
    if tail_pct is not None and tail_pct >= float(cfg.get("power_tail_pct", 0.75)):
        bonus = int(_number(cfg.get("power_candle_bonus_lots"), 1) or 0)
        lots += bonus
        factors.append(f"power_tail_{tail_pct:.2f}_+{bonus}")

    recovery_pct = _first_number(metadata, "recovery_pct", "body_recovery_pct")
    if recovery_pct is not None and recovery_pct >= float(cfg.get("power_recovery_pct", 0.95)):
        bonus = int(_number(cfg.get("power_candle_bonus_lots"), 1) or 0)
        lots += bonus
        factors.append(f"full_180_recovery_{recovery_pct:.2f}_+{bonus}")

    time_space_score = _first_number(metadata, "time_space_score")
    if time_space_score is not None and time_space_score >= float(cfg.get("high_quality_time_space_score", 0.8)):
        bonus = int(_number(cfg.get("high_quality_open_bonus_lots"), 1) or 0)
        lots += bonus
        factors.append(f"time_space_score_{time_space_score:.2f}_+{bonus}")

    if bool(cfg.get("allow_alert_lot_override", False)):
        override = _first_number(metadata, "sizing_lots", "lot_override", "lots")
        if override is not None:
            lots = int(override)
            factors.append(f"alert_lot_override_{lots}")

    cap_lots = max_lots
    if not locations:
        cap_lots = min(cap_lots, int(_number(cfg.get("missing_location_cap_lots"), 1) or 1))
        caps.append("missing_location_cap")
    if bool(metadata.get("chased")):
        cap_lots = min(cap_lots, int(_number(cfg.get("chased_cap_lots"), 2) or 2))
        caps.append("no_chase_limit_cap")
    if extended20 and not near200 and normalized_play not in CONTRARIAN_REVERSAL_PLAYS:
        cap_lots = min(cap_lots, int(_number(cfg.get("extended_continuation_cap_lots"), 1) or 1))
        caps.append("extended_continuation_defensive_cap")
    stop_pct = abs(float(entry_price) - float(stop_price)) / max(abs(float(entry_price)), 1e-9)
    wide_stop_threshold = float(max_stop_pct or 0.0) * float(cfg.get("wide_stop_pct_of_max", 0.5))
    if wide_stop_threshold > 0 and stop_pct >= wide_stop_threshold:
        cap_lots = min(cap_lots, int(_number(cfg.get("wide_stop_cap_lots"), 2) or 2))
        caps.append("wide_stop_defensive_cap")

    lots = max(1, min(int(lots), int(cap_lots), max_lots))
    label = f"{lots}/{max_lots} lots"
    if lots >= max_lots:
        label = f"{lots}/{max_lots} lots - full core"
    elif lots == 1:
        label = f"{lots}/{max_lots} lot - starter"
    return _plan(
        lots=lots,
        max_lots=max_lots,
        lot_fraction=lot_fraction,
        max_risk_budget=max_risk_budget,
        factors=factors,
        caps=caps,
        label=label,
    )


def normalize_locations(value: Any) -> List[str]:
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).lower().strip() for item in value if str(item).strip()]
    return [part.strip().lower() for part in str(value).replace(";", ",").split(",") if part.strip()]


def public_lot_config(config: Optional[dict]) -> dict:
    cfg = merged_lot_sizing_config(config)
    return {
        "enabled": bool(cfg.get("enabled", True)),
        "max_lots": int(_number(cfg.get("max_lots"), 4) or 4),
        "lot_risk_fraction": float(_number(cfg.get("lot_risk_fraction"), 0.25) or 0.25),
        "default_lots": int(_number(cfg.get("default_lots"), 1) or 1),
        "setup_base_lots": cfg.get("setup_base_lots", {}),
        "note": "Lots scale the risk budget; 4 lots equals the configured max trade risk, not 4x max risk.",
    }


def _plan(
    *,
    lots: int,
    max_lots: int,
    lot_fraction: float,
    max_risk_budget: float,
    factors: List[str],
    caps: List[str],
    label: str,
) -> dict:
    risk_fraction = min(1.0, max(0.0, float(lots) * float(lot_fraction)))
    effective_risk = round(float(max_risk_budget or 0.0) * risk_fraction, 2)
    return {
        "enabled": True,
        "lots": lots,
        "max_lots": max_lots,
        "label": label,
        "lot_risk_fraction": lot_fraction,
        "risk_fraction": round(risk_fraction, 4),
        "effective_risk_budget": effective_risk,
        "max_risk_budget": round(float(max_risk_budget or 0.0), 2),
        "factors": factors,
        "caps": caps,
    }


def _first_number(source: dict, *keys: str) -> Optional[float]:
    for key in keys:
        value = _number(source.get(key), None)
        if value is not None:
            return value
    return None


def _number(value: Any, default: Optional[float]) -> Optional[float]:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
