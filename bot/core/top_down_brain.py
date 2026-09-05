"""Top-down market context brain shared by Trading Bull bots.

The brain is deliberately advisory by default: it scores market wind, breadth,
sector flow, and strategy fit without silently deleting valid Velez setups.
Execution code can opt into stricter gating through config.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

from .types import Bar


DEFAULT_TOP_DOWN_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "mode": "advisory",
    "profile": "velez_intraday",
    "cache_seconds": 300,
    "daily_lookback": 80,
    "weekly_lookback": 52,
    "fast_sma": 20,
    "slow_sma": 50,
    "slope_lookback": 5,
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
    slope: float
    return_pct: Optional[float]
    bars: int

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "score": round(float(self.score), 3),
            "close": round(float(self.close), 4) if self.close is not None else None,
            "fast_sma": round(float(self.fast_sma), 4) if self.fast_sma is not None else None,
            "slow_sma": round(float(self.slow_sma), 4) if self.slow_sma is not None else None,
            "slope": round(float(self.slope), 6),
            "return_pct": round(float(self.return_pct), 4) if self.return_pct is not None else None,
            "bars": int(self.bars),
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
    cleaned_symbol = str(symbol or "").upper().strip()
    cleaned_side = str(side or "").lower().strip()
    daily = {sym.upper(): trend_signal(bars, cfg) for sym, bars in bars_by_symbol.items() if bars}
    weekly = {
        sym.upper(): trend_signal(resample_weekly(bars), {**cfg, "slow_sma": min(int(cfg.get("slow_sma", 50)), 30)})
        for sym, bars in bars_by_symbol.items()
        if bars
    }
    breadth = breadth_state(daily, cfg)
    sectors = sector_leadership_state(daily, config, cfg)
    symbol_sector = symbol_sector_state(cleaned_symbol, sectors)
    daily_bias = market_bias(daily, cfg, "daily")
    weekly_bias = market_bias(weekly, cfg, "weekly")
    regime = regime_label(daily_bias, weekly_bias, breadth)
    strategy_family = normalize_strategy_family(play)
    activation = strategy_activation(
        strategy_family=strategy_family,
        side=cleaned_side,
        daily_bias=daily_bias,
        weekly_bias=weekly_bias,
        breadth=breadth,
        sector=symbol_sector,
        regime=regime,
        confluence=confluence or {},
        cfg=cfg,
    )
    explanation = explain_state(
        symbol=cleaned_symbol,
        play=play,
        side=cleaned_side,
        timeframe=str((confluence or {}).get("signal_timeframe") or ""),
        daily_bias=daily_bias,
        weekly_bias=weekly_bias,
        breadth=breadth,
        sector=symbol_sector,
        regime=regime,
        activation=activation,
        confluence=confluence or {},
    )
    return {
        "ok": True,
        "enabled": True,
        "version": "top_down_brain_v1",
        "profile": str(cfg.get("profile") or "trading_bull"),
        "mode": str(cfg.get("mode") or "advisory").lower(),
        "generated_at": (generated_at or datetime.now(timezone.utc)).isoformat(),
        "symbol": cleaned_symbol or None,
        "play": play or None,
        "side": cleaned_side or None,
        "regime": regime,
        "confidence": confidence_score(daily_bias, weekly_bias, breadth, symbol_sector, confluence or {}),
        "daily_bias": daily_bias,
        "weekly_bias": weekly_bias,
        "breadth": breadth,
        "sector": symbol_sector,
        "sector_leadership": sectors,
        "strategy_family": strategy_family,
        "strategy_activation": activation,
        "explanation": explanation,
        "readback": explanation["summary"],
        "bias_by_symbol": {sym: sig.as_dict() for sym, sig in sorted(daily.items())},
        "guardrail": (
            "Advisory mode never removes a Velez setup by itself; gate mode must be explicitly configured."
            if str(cfg.get("mode") or "advisory").lower() == "advisory"
            else "Configured mode may reduce size or reject strategy/context mismatches."
        ),
    }


def trend_signal(bars: List[Bar], cfg: Mapping[str, Any]) -> TrendSignal:
    clean = [bar for bar in bars if getattr(bar, "close", None) is not None]
    if not clean:
        return TrendSignal("unknown", 0.0, None, None, None, 0.0, None, 0)
    closes = [float(bar.close) for bar in clean]
    close = closes[-1]
    fast_period = max(2, min(int(cfg.get("fast_sma", 20) or 20), len(closes)))
    slow_period = max(fast_period, min(int(cfg.get("slow_sma", 50) or 50), len(closes)))
    fast = sum(closes[-fast_period:]) / fast_period
    slow = sum(closes[-slow_period:]) / slow_period
    slope_lookback = max(1, min(int(cfg.get("slope_lookback", 5) or 5), len(closes) - 1))
    prior_fast = sum(closes[-fast_period - slope_lookback:-slope_lookback]) / fast_period if len(closes) >= fast_period + slope_lookback else closes[-1 - slope_lookback]
    slope = (fast - prior_fast) / max(close, 1e-9)
    lookback = max(1, min(int(cfg.get("sector_leadership", {}).get("lookback_bars", 20) or 20), len(closes) - 1))
    return_pct = (close - closes[-1 - lookback]) / max(closes[-1 - lookback], 1e-9)
    raw = 0.0
    raw += 0.35 if close > fast else -0.35
    raw += 0.35 if fast > slow else -0.35
    raw += max(-0.2, min(0.2, slope * 25))
    raw += max(-0.1, min(0.1, return_pct * 5))
    score = max(-1.0, min(1.0, raw))
    label = "bullish" if score >= 0.25 else "bearish" if score <= -0.25 else "neutral"
    return TrendSignal(label, score, close, fast, slow, slope, return_pct, len(clean))


def resample_weekly(bars: List[Bar]) -> List[Bar]:
    weeks: Dict[tuple, Bar] = {}
    for bar in sorted(bars, key=lambda item: item.timestamp):
        iso = bar.timestamp.isocalendar()
        key = (iso.year, iso.week)
        if key not in weeks:
            weeks[key] = Bar(timestamp=bar.timestamp, open=bar.open, high=bar.high, low=bar.low, close=bar.close, volume=bar.volume)
        else:
            prior = weeks[key]
            weeks[key] = Bar(timestamp=bar.timestamp, open=prior.open, high=max(prior.high, bar.high), low=min(prior.low, bar.low), close=bar.close, volume=float(prior.volume or 0) + float(bar.volume or 0))
    return [weeks[key] for key in sorted(weeks)]


def breadth_state(daily: Mapping[str, TrendSignal], cfg: Mapping[str, Any]) -> dict:
    symbols = [str(item).upper() for item in cfg.get("breadth", {}).get("symbols", ["SPY", "QQQ", "IWM"])]
    items = {sym: daily[sym].as_dict() for sym in symbols if sym in daily}
    bullish = sum(1 for sym in symbols if sym in daily and daily[sym].score >= 0.25)
    bearish = sum(1 for sym in symbols if sym in daily and daily[sym].score <= -0.25)
    available = len(items)
    supportive_min = int(cfg.get("breadth", {}).get("supportive_min", 2) or 2)
    hostile_min = int(cfg.get("breadth", {}).get("hostile_min", 2) or 2)
    label = "unknown" if available == 0 else "supportive" if bullish >= supportive_min else "hostile" if bearish >= hostile_min else "mixed"
    avg_score = sum(daily[sym].score for sym in symbols if sym in daily) / max(available, 1)
    return {"label": label, "score": round(avg_score, 3), "symbols": items, "bullish_count": bullish, "bearish_count": bearish, "available_count": available, "required_supportive": supportive_min, "readback": f"{bullish}/{available} breadth symbols bullish; {bearish}/{available} bearish."}


def market_bias(signals: Mapping[str, TrendSignal], cfg: Mapping[str, Any], timeframe: str) -> dict:
    symbols = [str(item).upper() for item in cfg.get("breadth", {}).get("symbols", ["SPY", "QQQ", "IWM"])]
    available = [signals[sym] for sym in symbols if sym in signals]
    if not available:
        return {"timeframe": timeframe, "label": "unknown", "score": 0.0, "available_count": 0, "readback": f"{timeframe} bias unavailable."}
    score = sum(item.score for item in available) / len(available)
    label = "bullish" if score >= 0.25 else "bearish" if score <= -0.25 else "neutral"
    return {"timeframe": timeframe, "label": label, "score": round(score, 3), "available_count": len(available), "readback": f"{timeframe.title()} market bias is {label} ({score:+.2f})."}


def sector_leadership_state(daily: Mapping[str, TrendSignal], root_config: Mapping[str, Any], cfg: Mapping[str, Any]) -> dict:
    if not cfg.get("sector_leadership", {}).get("enabled", True):
        return {"enabled": False, "groups": {}, "leaders": [], "laggards": []}
    sector_groups = root_config.get("strategy", {}).get("correlation", {}).get("sector_groups") or root_config.get("risk", {}).get("correlation", {}).get("sector_groups") or {}
    groups = {}
    for name, symbols in sector_groups.items():
        cleaned = [str(sym).upper() for sym in symbols if str(sym).upper() in daily]
        if not cleaned:
            continue
        avg = sum(daily[sym].score for sym in cleaned) / len(cleaned)
        groups[name] = {"symbols": cleaned, "score": round(avg, 3), "label": "leader" if avg >= 0.25 else "laggard" if avg <= -0.25 else "neutral"}
    leaders = sorted(({"sector": name, **data} for name, data in groups.items()), key=lambda item: item["score"], reverse=True)
    return {"enabled": True, "groups": groups, "leaders": leaders[:5], "laggards": sorted(leaders, key=lambda item: item["score"])[:5]}


def symbol_sector_state(symbol: str, sectors: Mapping[str, Any]) -> dict:
    for name, data in (sectors.get("groups") or {}).items():
        if symbol and symbol in set(data.get("symbols", [])):
            return {"name": name, **data}
    return {"name": "unmapped" if symbol else None, "label": "unknown", "score": 0.0, "symbols": [symbol] if symbol else []}


def regime_label(daily_bias: Mapping[str, Any], weekly_bias: Mapping[str, Any], breadth: Mapping[str, Any]) -> dict:
    daily = daily_bias.get("label")
    weekly = weekly_bias.get("label")
    breadth_label = breadth.get("label")
    if daily == "bullish" and weekly == "bullish" and breadth_label == "supportive":
        label = "risk_on_trend"
    elif daily == "bearish" and weekly == "bearish" and breadth_label == "hostile":
        label = "risk_off_trend"
    elif breadth_label in {"mixed", "unknown"} or daily != weekly:
        label = "mixed_or_transition"
    else:
        label = "selective"
    return {"label": label, "daily": daily, "weekly": weekly, "breadth": breadth_label}


def normalize_strategy_family(play: str) -> str:
    text = str(play or "").lower().replace("-", "_").replace(" ", "_")
    if "gap" in text and ("go" in text or "break" in text):
        return "opening_gap_go"
    if "gap" in text and "fade" in text:
        return "opening_gap_fade"
    if "180" in text or "one_eighty" in text:
        return "one_eighty_reversal"
    if "tail" in text:
        return "tail_reversal"
    if "failed" in text or "failure" in text:
        return "failed_breakout"
    if "buy" in text and "sell" in text:
        return "buy_sell_setup"
    if "nrb" in text or "acorn" in text:
        return "nrb_acorn"
    if "fab" in text:
        return "fab4"
    if "time" in text and "space" in text:
        return "time_space"
    if "elephant" in text:
        return "elephant"
    return text or "unknown"


def strategy_activation(*, strategy_family: str, side: str, daily_bias: Mapping[str, Any], weekly_bias: Mapping[str, Any], breadth: Mapping[str, Any], sector: Mapping[str, Any], regime: Mapping[str, Any], confluence: Mapping[str, Any], cfg: Mapping[str, Any]) -> dict:
    direction = 1 if side == "buy" else -1 if side == "sell" else 0
    bias_score = float(daily_bias.get("score") or 0) * 0.45 + float(weekly_bias.get("score") or 0) * 0.35 + float(breadth.get("score") or 0) * 0.20
    sector_score = float(sector.get("score") or 0)
    directional_fit = (bias_score + sector_score * 0.35) * (direction or 1)
    htf_action = str(confluence.get("action") or "unknown")
    htf_ok = htf_action in {"full_size", "unknown", ""}
    reversal_family = strategy_family in {"opening_gap_fade", "one_eighty_reversal", "tail_reversal", "failed_breakout"}
    continuation_family = strategy_family in {"opening_gap_go", "elephant", "buy_sell_setup", "nrb_acorn", "fab4", "time_space"}
    if reversal_family and abs(bias_score) > 0.75 and directional_fit < -0.15:
        status = "starter"
        reason = "Reversal setup against strong top-down wind; valid only as starter size until price confirms."
    elif continuation_family and directional_fit >= 0.25 and htf_ok:
        status = "active"
        reason = "Continuation setup agrees with daily/weekly bias, breadth, sector flow, and available higher-timeframe confluence."
    elif directional_fit <= -0.35:
        status = "watch"
        reason = "Top-down wind is opposed; keep the setup on watch or starter size unless the tape flips."
    elif not htf_ok:
        status = "starter"
        reason = f"Higher-timeframe confluence is {htf_action}; starter size only."
    else:
        status = "active"
        reason = "Market context is mixed but not hostile; setup remains available with normal guardrails."
    multiplier = {"active": 1.0, "starter": 0.5, "watch": 0.25, "inactive": 0.0}.get(status, 1.0)
    mode = str(cfg.get("mode") or "advisory").lower()
    return {"family": strategy_family, "status": status, "action": "explain" if mode == "advisory" else "size_adjust" if mode == "size" else "allow" if status in {"active", "starter"} else "reject", "executable": True if mode in {"advisory", "size"} else status in {"active", "starter"}, "size_multiplier": multiplier, "directional_fit": round(directional_fit, 3), "reason": reason}


def confidence_score(daily_bias: Mapping[str, Any], weekly_bias: Mapping[str, Any], breadth: Mapping[str, Any], sector: Mapping[str, Any], confluence: Mapping[str, Any]) -> float:
    score = 0.0
    score += 0.25 if daily_bias.get("label") != "unknown" else 0.0
    score += 0.20 if weekly_bias.get("label") != "unknown" else 0.0
    score += 0.25 if breadth.get("available_count", 0) >= 2 else 0.1 if breadth.get("available_count", 0) else 0.0
    score += 0.15 if sector.get("label") != "unknown" else 0.05
    score += 0.15 if confluence.get("enabled") else 0.05
    return round(min(score, 1.0), 3)


def explain_state(*, symbol: str, play: str, side: str, timeframe: str, daily_bias: Mapping[str, Any], weekly_bias: Mapping[str, Any], breadth: Mapping[str, Any], sector: Mapping[str, Any], regime: Mapping[str, Any], activation: Mapping[str, Any], confluence: Mapping[str, Any]) -> dict:
    tf = timeframe or "signal timeframe"
    higher = confluence.get("reason") or "higher-timeframe evidence unavailable"
    sector_name = sector.get("name") or "unmapped sector"
    sector_label = sector.get("label") or "unknown"
    summary = f"{symbol or 'The setup'} {play or activation.get('family', 'setup')} is {activation.get('status')} because {tf} signal context is checked against {higher}, daily bias is {daily_bias.get('label')}, weekly bias is {weekly_bias.get('label')}, breadth is {breadth.get('label')}, and {sector_name} sector flow is {sector_label}."
    return {"summary": " ".join(summary.split()), "bullets": [daily_bias.get("readback", "Daily bias unavailable."), weekly_bias.get("readback", "Weekly bias unavailable."), breadth.get("readback", "Breadth unavailable."), f"Sector flow: {sector_name} is {sector_label} ({float(sector.get('score') or 0):+.2f}).", f"Strategy activation: {activation.get('status')} — {activation.get('reason')}"], "winston_prompt_hint": "Explain whether this setup is valid because the signal timeframe agrees with higher timeframes, daily/weekly bias, SPY/QQQ/IWM breadth, and sector flow.", "regime": regime.get("label")}
