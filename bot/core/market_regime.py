"""
Market Regime Detection — classifies current market conditions.

Feeds into lot sizing: trending = full lots, ranging = reduced,
volatile = caution. Each regime has a confidence score 0-1.

Regimes:
  - trending_up / trending_down — strong directional, stacking bars
  - ranging — price oscillating around SMA, frequent wicks
  - volatile — ATR expansion, wide ranges
  - quiet — ATR contraction, narrow ranges
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .indicators import RollingATR, RollingSMA
from .types import Bar
from .velez_extensions import candle_shape


# ── Config ───────────────────────────────────────────────────────────

REGIME_KEY = "market_regime"

DEFAULT_CONFIG = {
    "enabled": True,
    "lookback_bars": 50,
    "atr_lookback": 14,
    "trend_sma": 20,
    "trend_strength_bars": 10,        # consecutive same-side closes for trend
    "range_bound_pct": 0.015,         # max 1.5% SMA deviation to be "ranging"
    "volatile_atr_mult": 2.0,         # ATR vs 50-bar avg → volatile if >2x
    "quiet_atr_mult": 0.5,            # ATR vs 50-bar avg → quiet if <0.5x
    "min_bars_for_regime": 20,        # minimum bars before classification
}


class MarketRegime:
    trending_up: bool
    trending_down: bool
    ranging: bool
    volatile: bool
    quiet: bool
    confidence: float  # 0-1
    label: str
    atr_percent: float

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __repr__(self) -> str:
        return (f"Regime({self.label}, conf={self.confidence}, "
                f"atr_pct={self.atr_percent:.2f}%)")


def classify_regime(
    bars: List[Bar],
    config: dict,
) -> MarketRegime:
    """Analyze recent bars and return the detected market regime."""
    rc = {**DEFAULT_CONFIG, **(config.get(REGIME_KEY, {}) or {})}
    if not rc["enabled"] or len(bars) < rc["min_bars_for_regime"]:
        return MarketRegime(
            trending_up=False, trending_down=False,
            ranging=True, volatile=False, quiet=False,
            confidence=0.5, label="unknown",
            atr_percent=0.0,
        )

    recent = bars[-rc["lookback_bars"]:]
    closes = [b.close for b in recent]
    sma20 = sum(closes[-rc["trend_sma"]:]) / max(rc["trend_sma"], 1)

    # ATR and volatility
    ranges = [b.high - b.low for b in recent]
    avg_atr = sum(ranges[-rc["atr_lookback"]:]) / max(rc["atr_lookback"], 1)
    long_avg_atr = sum(ranges) / max(len(ranges), 1)
    atr_ratio = avg_atr / max(long_avg_atr, 1e-9)
    atr_pct = avg_atr / max(closes[-1], 1e-9) * 100

    # Trend strength: % of bars above/below SMA in recent window
    above_sma = sum(1 for c in closes[-rc["trend_strength_bars"]:] if c > sma20)
    total = max(rc["trend_strength_bars"], 1)
    trend_ratio = above_sma / total

    # Distance from SMA
    price_vs_sma = abs(closes[-1] - sma20) / max(sma20, 1e-9)

    # Wicks (both sides = choppy)
    wick_count = 0
    for b in recent[-10:]:
        sh = candle_shape(b)
        if sh["upper_wick"] / max(sh["range"], 1e-9) > 0.4 and \
           sh["lower_wick"] / max(sh["range"], 1e-9) > 0.4:
            wick_count += 1

    # Classify
    trending_up = trend_ratio >= 0.7 and price_vs_sma < 0.02
    trending_down = trend_ratio <= 0.3 and price_vs_sma < 0.02
    volatile = atr_ratio >= rc["volatile_atr_mult"]
    quiet = atr_ratio <= rc["quiet_atr_mult"]
    ranging = not (trending_up or trending_down) and price_vs_sma < rc["range_bound_pct"]

    # Confidence
    conf_factors = []
    if trending_up or trending_down:
        conf_factors.append(min(abs(trend_ratio - 0.5) * 2, 1.0))
    if ranging:
        conf_factors.append(max(0, 1 - price_vs_sma / rc["range_bound_pct"]))
    if volatile:
        conf_factors.append(min(atr_ratio / rc["volatile_atr_mult"], 1.0))
    if quiet:
        conf_factors.append(max(0, 1 - atr_ratio / rc["quiet_atr_mult"]))
    confidence = round(sum(conf_factors) / max(len(conf_factors), 1), 2) if conf_factors else 0.5

    # Label
    if volatile:
        label = "volatile"
    elif trending_up:
        label = "trending_up"
    elif trending_down:
        label = "trending_down"
    elif ranging:
        label = "ranging"
    elif quiet:
        label = "quiet"
    else:
        label = "mixed"

    return MarketRegime(
        trending_up=trending_up,
        trending_down=trending_down,
        ranging=ranging,
        volatile=volatile,
        quiet=quiet,
        confidence=confidence,
        label=label,
        atr_percent=round(atr_pct, 2),
    )


def regime_lot_multiplier(regime: MarketRegime) -> float:
    """Return lot sizing multiplier based on regime.

    Trending → 1.0 (full size), Ranging → 0.6, Volatile → 0.4
    """
    if regime.trending_up or regime.trending_down:
        return 1.0
    if regime.ranging:
        return 0.6
    if regime.volatile:
        return 0.4
    if regime.quiet:
        return 0.8
    return 0.7
