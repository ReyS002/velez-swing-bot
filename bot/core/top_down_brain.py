"""Top-down market context brain for Trading Bull Swing.

Scores daily/weekly bias, SPY/QQQ/IWM breadth, sector leadership, and whether
the current setup has market wind. Advisory mode never removes a Velez setup.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional

from .types import Bar


DEFAULT_TOP_DOWN_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "mode": "advisory",
    "profile": "velez_swing",
    "cache_seconds": 300,
    "daily_lookback": 120,
    "weekly_lookback": 52,
    "fast_sma": 20,
    "slow_sma": 50,
    "breadth": {"symbols": ["SPY", "QQQ", "IWM"], "supportive_min": 2, "hostile_min": 2},
    "sector_leadership": {"enabled": True, "lookback_bars": 20},
    "strategy_activation": {"enabled": True, "default_action": "active", "advisory_min_multiplier": 0.5},
}


@dataclass(frozen=True)
class TrendSignal:
    label: str
    score: float
    close: Optional[float]
    fast_sma: Optional[float]
    slow_sma: Optional[float]
    return_pct: Optional[float]
    bars: int

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "score": round(self.score, 3),
            "close": round(self.close, 4) if self.close is not None else None,
            "fast_sma": round(self.fast_sma, 4) if self.fast_sma is not None else None,
            "slow_sma": round(self.slow_sma, 4) if self.slow_sma is not None else None,
            "return_pct": round(self.return_pct, 4) if self.return_pct is not None else None,
            "bars": self.bars,
        }


def merged_top_down_config(config: Mapping[str, Any]) -> Dict[str, Any]:
    supplied = dict(config.get("top_down", {}) or {})
    merged = {**DEFAULT_TOP_DOWN_CONFIG, **supplied}
    merged["breadth"] = {**DEFAULT_TOP_DOWN_CONFIG["breadth"], **(supplied.get("breadth", {}) or {})}
    merged["sector_leadership"] = {**DEFAULT_TOP_DOWN_CONFIG["sector_leadership"], **(supplied.get("sector_leadership", {}) or {})}
    merged["strategy_activation"] = {**DEFAULT_TOP_DOWN_CONFIG["strategy_activation"], **(supplied.get("strategy_activation", {}) or {})}
    return merged


def build_top_down_state(
    config: Mapping[str, Any],
    bars_by_symbol: Mapping[str, List[Bar]],
    *,
    symbol: str = "",
    play: str = "",
    side: str = "",
    confluence: Optional[Mapping[str, Any]] = None,
    generated_at: Optional[datetime] = None,
) -> dict:
    cfg = merged_top_down_config(config)
    if not cfg.get("enabled", True):
        return {"ok": True, "enabled": False, "mode": "disabled", "summary": "Top-down analysis is disabled."}
    daily = {sym.upper(): trend_signal(bars, cfg) for sym, bars in bars_by_symbol.items() if bars}
    weekly = {sym.upper(): trend_signal(resample_weekly(bars), {**cfg, "slow_sma": 30}) for sym, bars in bars_by_symbol.items() if bars}
    breadth = breadth_state(daily, cfg)
    sectors = sector_leadership_state(daily, config, cfg)
    sector = symbol_sector_state(str(symbol or "").upper(), sectors)
    daily_bias = market_bias(daily, cfg, "daily")
    weekly_bias = market_bias(weekly, cfg, "weekly")
    regime = regime_label(daily_bias, weekly_bias, breadth)
    family = normalize_strategy_family(play)
    activation = strategy_activation(family, side, daily_bias, weekly_bias, breadth, sector, confluence or {}, cfg)
    readback = (
        f"{str(symbol or 'Setup').upper()} {play or family} is {activation['status']} because daily bias is "
        f"{daily_bias['label']}, weekly bias is {weekly_bias['label']}, breadth is {breadth['label']}, "
        f"and {sector.get('name') or 'sector'} flow is {sector.get('label', 'unknown')}."
    )
    return {
        "ok": True,
        "enabled": True,
        "version": "top_down_brain_v1",
        "profile": str(cfg.get("profile") or "velez_swing"),
        "mode": str(cfg.get("mode") or "advisory").lower(),
        "generated_at": (generated_at or datetime.utcnow()).isoformat(),
        "symbol": str(symbol or "").upper() or None,
        "play": play or None,
        "side": str(side or "").lower() or None,
        "regime": regime,
        "confidence": confidence_score(daily_bias, weekly_bias, breadth, sector, confluence or {}),
        "daily_bias": daily_bias,
        "weekly_bias": weekly_bias,
        "breadth": breadth,
        "sector": sector,
        "sector_leadership": sectors,
        "strategy_family": family,
        "strategy_activation": activation,
        "readback": readback,
        "explanation": {
            "summary": readback,
            "bullets": [
                daily_bias["readback"],
                weekly_bias["readback"],
                breadth["readback"],
                f"Sector flow: {sector.get('name') or 'unmapped'} is {sector.get('label', 'unknown')}.",
                f"Strategy activation: {activation['status']} — {activation['reason']}",
            ],
            "winston_prompt_hint": "Explain if the setup agrees with higher timeframe, daily/weekly bias, breadth, and sector flow.",
        },
        "bias_by_symbol": {sym: sig.as_dict() for sym, sig in sorted(daily.items())},
        "guardrail": "Advisory mode never removes a Velez setup by itself; gate mode must be explicitly configured.",
    }


def trend_signal(bars: List[Bar], cfg: Mapping[str, Any]) -> TrendSignal:
    closes = [float(bar.close) for bar in bars if getattr(bar, "close", None) is not None]
    if len(closes) < 2:
        return TrendSignal("unknown", 0.0, closes[-1] if closes else None, None, None, None, len(closes))
    close = closes[-1]
    fast_n = max(2, min(int(cfg.get("fast_sma", 20) or 20), len(closes)))
    slow_n = max(fast_n, min(int(cfg.get("slow_sma", 50) or 50), len(closes)))
    fast = sum(closes[-fast_n:]) / fast_n
    slow = sum(closes[-slow_n:]) / slow_n
    lookback = max(1, min(int(cfg.get("sector_leadership", {}).get("lookback_bars", 20) or 20), len(closes) - 1))
    ret = (close - closes[-1 - lookback]) / max(closes[-1 - lookback], 1e-9)
    score = (0.4 if close > fast else -0.4) + (0.4 if fast > slow else -0.4) + max(-0.2, min(0.2, ret * 5))
    score = max(-1.0, min(1.0, score))
    label = "bullish" if score >= 0.25 else "bearish" if score <= -0.25 else "neutral"
    return TrendSignal(label, score, close, fast, slow, ret, len(closes))


def resample_weekly(bars: List[Bar]) -> List[Bar]:
    weeks: Dict[tuple, Bar] = {}
    for bar in sorted(bars, key=lambda item: item.timestamp):
        iso = bar.timestamp.isocalendar()
        key = (iso.year, iso.week)
        if key not in weeks:
            weeks[key] = Bar(bar.timestamp, bar.open, bar.high, bar.low, bar.close, bar.volume)
        else:
            prior = weeks[key]
            weeks[key] = Bar(bar.timestamp, prior.open, max(prior.high, bar.high), min(prior.low, bar.low), bar.close, float(prior.volume or 0) + float(bar.volume or 0))
    return [weeks[key] for key in sorted(weeks)]


def breadth_state(daily: Mapping[str, TrendSignal], cfg: Mapping[str, Any]) -> dict:
    symbols = [str(item).upper() for item in cfg.get("breadth", {}).get("symbols", ["SPY", "QQQ", "IWM"])]
    available = [daily[sym] for sym in symbols if sym in daily]
    bullish = sum(1 for item in available if item.score >= 0.25)
    bearish = sum(1 for item in available if item.score <= -0.25)
    label = "unknown" if not available else "supportive" if bullish >= int(cfg.get("breadth", {}).get("supportive_min", 2)) else "hostile" if bearish >= int(cfg.get("breadth", {}).get("hostile_min", 2)) else "mixed"
    score = sum(item.score for item in available) / max(len(available), 1)
    return {"label": label, "score": round(score, 3), "bullish_count": bullish, "bearish_count": bearish, "available_count": len(available), "symbols": {sym: daily[sym].as_dict() for sym in symbols if sym in daily}, "readback": f"{bullish}/{len(available)} breadth symbols bullish; {bearish}/{len(available)} bearish."}


def market_bias(signals: Mapping[str, TrendSignal], cfg: Mapping[str, Any], timeframe: str) -> dict:
    symbols = [str(item).upper() for item in cfg.get("breadth", {}).get("symbols", ["SPY", "QQQ", "IWM"])]
    available = [signals[sym] for sym in symbols if sym in signals]
    if not available:
        return {"timeframe": timeframe, "label": "unknown", "score": 0.0, "available_count": 0, "readback": f"{timeframe} bias unavailable."}
    score = sum(item.score for item in available) / len(available)
    label = "bullish" if score >= 0.25 else "bearish" if score <= -0.25 else "neutral"
    return {"timeframe": timeframe, "label": label, "score": round(score, 3), "available_count": len(available), "readback": f"{timeframe.title()} market bias is {label} ({score:+.2f})."}


def sector_leadership_state(daily: Mapping[str, TrendSignal], root_config: Mapping[str, Any], cfg: Mapping[str, Any]) -> dict:
    groups_cfg = root_config.get("strategy", {}).get("correlation", {}).get("sector_groups") or root_config.get("risk", {}).get("correlation", {}).get("sector_groups") or {}
    groups = {}
    for name, symbols in groups_cfg.items():
        members = [str(sym).upper() for sym in symbols if str(sym).upper() in daily]
        if members:
            score = sum(daily[sym].score for sym in members) / len(members)
            groups[name] = {"symbols": members, "score": round(score, 3), "label": "leader" if score >= 0.25 else "laggard" if score <= -0.25 else "neutral"}
    leaders = sorted(({"sector": name, **data} for name, data in groups.items()), key=lambda item: item["score"], reverse=True)
    return {"enabled": True, "groups": groups, "leaders": leaders[:5], "laggards": sorted(leaders, key=lambda item: item["score"])[:5]}


def symbol_sector_state(symbol: str, sectors: Mapping[str, Any]) -> dict:
    for name, data in (sectors.get("groups") or {}).items():
        if symbol and symbol in data.get("symbols", []):
            return {"name": name, **data}
    return {"name": "unmapped" if symbol else None, "label": "unknown", "score": 0.0, "symbols": [symbol] if symbol else []}


def regime_label(daily_bias: Mapping[str, Any], weekly_bias: Mapping[str, Any], breadth: Mapping[str, Any]) -> dict:
    if daily_bias["label"] == "bullish" and weekly_bias["label"] == "bullish" and breadth["label"] == "supportive":
        label = "risk_on_trend"
    elif daily_bias["label"] == "bearish" and weekly_bias["label"] == "bearish" and breadth["label"] == "hostile":
        label = "risk_off_trend"
    elif daily_bias["label"] != weekly_bias["label"] or breadth["label"] in {"mixed", "unknown"}:
        label = "mixed_or_transition"
    else:
        label = "selective"
    return {"label": label, "daily": daily_bias["label"], "weekly": weekly_bias["label"], "breadth": breadth["label"]}


def normalize_strategy_family(play: str) -> str:
    text = str(play or "").lower().replace("-", "_").replace(" ", "_")
    if "gap" in text and "fade" in text:
        return "opening_gap_fade"
    if "gap" in text:
        return "opening_gap_go"
    if "180" in text or "one_eighty" in text:
        return "one_eighty_reversal"
    if "tail" in text:
        return "tail_reversal"
    if "failed" in text:
        return "failed_breakout"
    if "elephant" in text:
        return "elephant"
    return text or "unknown"


def strategy_activation(family: str, side: str, daily_bias: Mapping[str, Any], weekly_bias: Mapping[str, Any], breadth: Mapping[str, Any], sector: Mapping[str, Any], confluence: Mapping[str, Any], cfg: Mapping[str, Any]) -> dict:
    direction = 1 if str(side).lower() == "buy" else -1 if str(side).lower() == "sell" else 1
    fit = (float(daily_bias["score"]) * 0.4 + float(weekly_bias["score"]) * 0.4 + float(breadth["score"]) * 0.2 + float(sector.get("score") or 0) * 0.25) * direction
    if fit >= 0.25:
        status, reason = "active", "Setup agrees with daily/weekly bias, breadth, and sector flow."
    elif fit <= -0.35:
        status, reason = "watch", "Top-down wind is opposed; keep as watch/starter unless price confirms."
    else:
        status, reason = "active", "Market context is mixed but not hostile; normal guardrails still apply."
    mode = str(cfg.get("mode") or "advisory").lower()
    return {"family": family, "status": status, "action": "explain" if mode == "advisory" else "size_adjust" if mode == "size" else "allow" if status == "active" else "reject", "executable": mode in {"advisory", "size"} or status == "active", "size_multiplier": 1.0 if status == "active" else 0.25, "directional_fit": round(fit, 3), "reason": reason}


def confidence_score(daily_bias: Mapping[str, Any], weekly_bias: Mapping[str, Any], breadth: Mapping[str, Any], sector: Mapping[str, Any], confluence: Mapping[str, Any]) -> float:
    score = 0.25 if daily_bias["label"] != "unknown" else 0
    score += 0.25 if weekly_bias["label"] != "unknown" else 0
    score += 0.25 if breadth.get("available_count", 0) >= 2 else 0
    score += 0.15 if sector.get("label") != "unknown" else 0.05
    score += 0.10 if confluence.get("enabled") else 0.05
    return round(min(score, 1.0), 3)
