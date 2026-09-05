"""
Velez Strategy Extensions — Swing bot subset (4 strategies).
W-shape recovery, stacking score, wick counting, give me a C.
"""
from __future__ import annotations
from typing import List, Optional, Tuple
from .types import Bar, Signal, Side
from .utils import safe_div

def candle_shape(bar):
    body = abs(bar.close - bar.open)
    rng = max(bar.high - bar.low, 1e-9)
    return {"body": body, "range": rng, "upper_wick": max(bar.high - max(bar.open, bar.close), 0.0), "lower_wick": max(min(bar.open, bar.close) - bar.low, 0.0), "bullish": bar.close > bar.open}

def w_shape_signals(symbol, bar, ctx_bars, atr, cfg):
    enabled = cfg.get("w_shape", {}).get("enabled", True)
    if not enabled or len(ctx_bars) < 4: return []
    decline_bars = cfg.get("w_shape", {}).get("decline_bars", 2)
    recent = ctx_bars[-(decline_bars + 2):]
    if len(recent) < decline_bars + 2: return []
    decline = recent[:-2]
    if not all(b.close < b.open for b in decline if b): return []
    decline_low = min(b.low for b in decline)
    decline_range = max(b.high for b in decline) - decline_low
    if decline_range <= 0: return []
    if not candle_shape(bar)["bullish"]: return []
    recovery = (bar.close - decline_low) / decline_range
    if recovery < cfg.get("w_shape", {}).get("recovery_pct", 0.50): return []
    stop = min(b.low for b in recent) - (atr or 0.5) * 0.3
    bar2 = recent[-2]
    if bar2.close < bar2.open:
        return [Signal(symbol, Side.BUY, "v_shape", {"play": "elephant_bar", "stop_price": stop, "trigger_price": bar.close, "shape_type": "v", "confidence": round(min(recovery, 1.0) * 0.7, 2)})]
    retest = abs(bar2.low - decline_low) / max(decline_range, 0.01) < 0.002
    if retest and bar2.close < bar2.open:
        return [Signal(symbol, Side.BUY, "w_shape", {"play": "bottoming_tail", "stop_price": stop, "trigger_price": bar.close, "shape_type": "w", "confidence": round(min(recovery, 1.0) * 0.9, 2)})]
    return []

def stacking_score(ctx_bars, sma20, side, cfg):
    sc = cfg.get("stacking", {})
    if not sc.get("enabled", True) or sma20 is None or len(ctx_bars) < 3: return 0.0
    lookback = min(sc.get("lookback", 20), len(ctx_bars) - 1)
    recent = ctx_bars[-lookback:]
    gap = sc.get("gap_bars", 5)
    is_bull = side == Side.BUY
    same = sum(1 for b in reversed(recent) if (b.close > sma20) == is_bull)
    ss = min(same / max(gap, 1), 1.0)
    no_overlap = 0
    for i in range(1, min(len(recent), gap)):
        p, c = recent[-(i + 1)], recent[-i]
        if (c.low > p.high) if is_bull else (c.high < p.low): no_overlap += 1
    os = no_overlap / max(gap, 1)
    bodies = sum(1 for b in recent[-gap:] if (b.close > b.open) == is_bull)
    bs = bodies / max(gap, 1)
    return round(ss * 0.5 + os * 0.3 + bs * 0.2, 2)

def give_me_a_c_signals(symbol, bar, ctx_bars, atr, cfg):
    cc = cfg.get("give_me_a_c", {})
    if not cc.get("enabled", True) or len(ctx_bars) < 3: return []
    b1, b2 = ctx_bars[-3], ctx_bars[-2]
    if b1.close >= b1.open or b2.low >= b1.low: return []
    if not (bar.close > bar.open and bar.close > b1.close): return []
    stop = b2.low - (atr or 0.5) * 0.2
    return [Signal(symbol, Side.BUY, "give_me_a_c", {"play": "velez_buy_setup", "stop_price": stop, "trigger_price": bar.close, "pivot_low": round(b2.low, 2)})]

def wick_exhaustion_warning(ctx_bars, side, cfg):
    wc = cfg.get("wick_counting", {})
    if not wc.get("enabled", True) or len(ctx_bars) < 3: return False, 0, 0.0
    lookback = min(wc.get("lookback", 8), len(ctx_bars) - 1)
    recent = ctx_bars[-lookback:]
    thresh = wc.get("wick_threshold", 0.5)
    count = 0; sev = 0.0
    for b in reversed(recent):
        sh = candle_shape(b)
        wick = sh["upper_wick"] if side == Side.BUY else sh["lower_wick"]
        wick_pct = wick / max(b.high - b.low, 1e-9)
        if wick_pct >= thresh: count += 1; sev += wick_pct
        else: break
    if count >= wc.get("min_consecutive", 2): return True, count, round(min(sev / count, 1.0), 2)
    return False, count, 0.0

def run_extensions(symbol, bar, ctx_bars, bodies, sma20, atr, cfg, is_swing=False):
    signals = []
    signals.extend(w_shape_signals(symbol, bar, ctx_bars, atr, cfg))
    signals.extend(give_me_a_c_signals(symbol, bar, ctx_bars, atr, cfg))
    for sig in signals:
        sig.metadata["stacking_score"] = stacking_score(ctx_bars, sma20, sig.side, cfg)
        ex, cnt, sev = wick_exhaustion_warning(ctx_bars, sig.side, cfg)
        sig.metadata["wick_exhaustion"] = ex
        sig.metadata["wick_count"] = cnt
        sig.metadata["wick_severity"] = sev
    return signals
