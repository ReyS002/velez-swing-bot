#!/usr/bin/env python3
"""
velez-mcp doctrine layer — Oliver Velez rules as deterministic, testable code.

Pure Python, no dependency on the VPS trading bot. Everything here answers
"what would Velez say about this chart / this trade?" from raw OHLC bars:

  market_state    — 20/200 SMA read: trend, 200 veto, narrow / trending / wide state,
                    location, Fab 4 trap zone.
  classify_candle — event-bar vocabulary: elephant (igniting / continuation /
                    exhausting), tails, 180s, RBI/GBI, NRB, doji.
  checklist       — grade a long/short idea against the Velez rules.
  trade_plan      — event-bar entry, event stop, MLPT, lots, targets, adds.
  manage_position — bar-by-bar trail, 3-bar rule, breakeven, partials,
                    opposing-event exits.
  playbook        — the rules themselves, searchable.

Thresholds default to the same numbers the bot's `velez_strategy` config uses
so this layer and the engine speak the same language.

This file is the single Velez rulebook. The bots (velez-trading-bot,
velez-swing-bot, bull-pilot, bull-swarm) vendor it byte-for-byte as
`velez_doctrine.py`. Change it here, bump DOCTRINE_VERSION, then re-copy.
"""
from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone
from typing import Any, Iterable, Optional

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None

DOCTRINE_VERSION = "2026.10.2"

# ── Defaults (mirror bot/config.yaml → velez_strategy where one exists) ──

SMA_FAST = 20
SMA_SLOW = 200
ATR_PERIOD = 14
SLOPE_LOOKBACK = 5
NEAR_SMA_PCT = 0.0025
NEAR_SMA_ATR_MULT = 0.35
EXTENDED_SMA_PCT = 0.012
EXTENDED_SMA_ATR_MULT = 1.0
NARROW_STATE_PCT = 0.004   # strategy.narrow_threshold
WIDE_STATE_PCT = 0.008     # strategy.wide_threshold
SLOPE_FLAT_ATR = 0.1       # |ΔSMA over lookback| below this × ATR = flat
# 20 SMA slant, in ATR per bar. "45 degrees" depends on chart scaling, so the
# slant is measured against volatility: flat → steady (the 45° ramp) → steep.
SLANT_FLAT_ATR_PER_BAR = 0.02
SLANT_STEEP_ATR_PER_BAR = 0.3
SLANT_ACCEL_RATIO = 2.0    # slope now vs. slope one lookback earlier = curving
FAB4_RANGE_BARS = 30       # ≈ last 60 minutes on a 2-minute chart
ELEPHANT_BODY_MULT = 1.8
ELEPHANT_BODY_LOOKBACK = 5
ELEPHANT_MAX_WICK_PCT = 0.2
ELEPHANT_MAX_TOTAL_WICK_PCT = 0.35
TAIL_PCT = 0.66
ONE_EIGHTY_RECOVER_PCT = 0.8
NRB_RANGE_MULT = 0.65
NRB_LOOKBACK = 7
# Three-finger spread: distance from the 20 SMA in ATRs of the chart being traded.
TFS_CAUTION_ATR = 2.0
TFS_BLOCK_ATR = 3.0
MIDDAY_START = time(11, 30)
MIDDAY_END = time(13, 30)
SESSION_OPEN = time(9, 30)
MARKET_TZ = "America/New_York"
# Session discipline for new entries (US equities, ET). Velez: let amateur hour
# settle, skip the midday chop, and don't open new trades into the close.
OPENING_WAIT_MIN = 15          # no new entries in the first 15 minutes
GAP_OPENING_WAIT_MIN = 5       # opening-gap plays may act after the first 5 minutes
LAST_ENTRY = time(15, 45)      # no new entries in the last 15 minutes
SESSION_CLOSE = time(16, 0)
GAP_PLAYS = {"opening_gap_go", "opening_gap_fade", "gap_and_go", "gap_fade_to_prior_close", "opening_gap", "opening_gap_time_space"}

CONTINUATION_PLAYS = {
    "velez_buy_setup", "velez_sell_setup", "buy_setup", "sell_setup",
    "color_change_add", "rbi", "gbi", "red_bar_ignored", "green_bar_ignored",
    "nrb_acorn", "three_bar_play", "elephant_bar", "igniting_elephant",
    "opening_gap_go", "time_space_breakout", "fab4_trap_breakout",
    "pullback_tail",
}
# Plays whose signal bar IS the event bar: Velez enters on the break of it,
# not at its close.
EVENT_BAR_PLAYS = {
    "elephant_bar", "bull_180", "bear_180", "bottoming_tail", "topping_tail",
    "failed_new_high", "failed_new_low",
}
REVERSAL_PLAYS = {
    "bottoming_tail", "topping_tail", "bull_180", "bear_180",
    "failed_new_high", "failed_new_low", "opening_gap_fade",
}


# ── Bar parsing ──

def parse_bars(bars: Any) -> list[dict[str, Any]]:
    """Accept a JSON string or list of {o,h,l,c,v,t} (or long-name) bars."""
    if isinstance(bars, str):
        bars = json.loads(bars) if bars.strip() else []
    out: list[dict[str, Any]] = []
    for raw in bars or []:
        o = float(raw.get("o", raw.get("open")))
        h = float(raw.get("h", raw.get("high")))
        l = float(raw.get("l", raw.get("low")))
        c = float(raw.get("c", raw.get("close")))
        v = float(raw.get("v", raw.get("volume", 0)) or 0)
        out.append({"o": o, "h": h, "l": l, "c": c, "v": v,
                    "t": parse_timestamp(raw.get("t", raw.get("timestamp")))})
    return out


def parse_timestamp(value: Any) -> Optional[datetime]:
    """ISO-8601 string or epoch (s or ms) → tz-aware UTC datetime; None if absent."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        seconds = value / 1000.0 if value > 1e11 else float(value)
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    text = str(value).strip()
    if text.replace(".", "", 1).isdigit():
        return parse_timestamp(float(text))
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def bar_dict(bar: Any) -> dict[str, Any]:
    """Adapt an engine Bar (open/high/low/close/volume/timestamp) or a dict to this module's shape."""
    if isinstance(bar, dict) and "o" in bar:
        return bar
    get = (lambda k: bar.get(k)) if isinstance(bar, dict) else (lambda k: getattr(bar, k, None))
    return {
        "o": float(get("open")), "h": float(get("high")), "l": float(get("low")), "c": float(get("close")),
        "v": float(get("volume") or 0), "t": parse_timestamp(get("timestamp")),
    }


def break_trigger(side: str, event_high: float, event_low: float, tick: float = 0.01) -> float:
    """The price that confirms an event bar: one tick through its high (long) or low (short)."""
    return event_high + tick if _norm_side(side) == "long" else event_low - tick


def _local(ts: Optional[datetime]) -> Optional[datetime]:
    if ts is None or ZoneInfo is None:
        return ts
    try:
        return ts.astimezone(ZoneInfo(MARKET_TZ))
    except Exception:  # no tz database in the container: fall back to UTC
        return ts


# ── Indicators ──

def sma(values: list[float], period: int, offset: int = 0) -> Optional[float]:
    """Simple moving average ending `offset` bars before the last value."""
    end = len(values) - offset
    if period <= 0 or end < period:
        return None
    window = values[end - period:end]
    return sum(window) / period


def atr(bars: list[dict[str, Any]], period: int = ATR_PERIOD) -> Optional[float]:
    if len(bars) < 2:
        return None
    trs = []
    for prev, cur in zip(bars, bars[1:]):
        trs.append(max(cur["h"] - cur["l"], abs(cur["h"] - prev["c"]), abs(cur["l"] - prev["c"])))
    window = trs[-period:]
    return sum(window) / len(window) if window else None


def _slope_label(now: Optional[float], before: Optional[float], atr_value: Optional[float]) -> Optional[str]:
    if now is None or before is None:
        return None
    change = now - before
    flat_band = SLOPE_FLAT_ATR * atr_value if atr_value else abs(now) * 0.0005
    if change > flat_band:
        return "rising"
    if change < -flat_band:
        return "falling"
    return "flat"


# ── Candle anatomy + Velez event vocabulary ──

def anatomy(bar: dict[str, Any]) -> dict[str, Any]:
    body = abs(bar["c"] - bar["o"])
    rng = max(bar["h"] - bar["l"], 0.0)
    upper = max(bar["h"] - max(bar["o"], bar["c"]), 0.0)
    lower = max(min(bar["o"], bar["c"]) - bar["l"], 0.0)
    safe = rng if rng > 0 else 1e-9
    return {
        "body": body, "range": rng, "upper_wick": upper, "lower_wick": lower,
        "body_pct": body / safe, "upper_wick_pct": upper / safe, "lower_wick_pct": lower / safe,
        "bullish": bar["c"] > bar["o"], "bearish": bar["c"] < bar["o"],
        "color": "green" if bar["c"] > bar["o"] else "red" if bar["c"] < bar["o"] else "doji",
        "body_midpoint": (bar["o"] + bar["c"]) / 2.0,
    }


def classify_candle(bar: dict[str, Any], prior: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    """Name the Velez events printed by `bar`, given the bars before it.

    Single-bar events (tails, doji) need no history. Elephant, 180, NRB,
    RBI/GBI and igniting-vs-exhausting need `prior` bars; with ≥20 prior bars
    the elephant is also classified by where it ORIGINATES relative to the 20.
    """
    prior = prior or []
    a = anatomy(bar)
    events: list[str] = []
    detail: dict[str, Any] = {}

    if a["range"] > 0 and a["lower_wick_pct"] >= TAIL_PCT:
        events.append("bottoming_tail")
    if a["range"] > 0 and a["upper_wick_pct"] >= TAIL_PCT:
        events.append("topping_tail")
    if a["range"] > 0 and a["body_pct"] <= 0.1:
        events.append("doji")

    if len(prior) >= ELEPHANT_BODY_LOOKBACK and a["range"] > 0:
        recent = prior[-ELEPHANT_BODY_LOOKBACK:]
        avg_body = sum(anatomy(b)["body"] for b in recent) / len(recent)
        wick_ok = (
            a["upper_wick_pct"] <= ELEPHANT_MAX_WICK_PCT
            and a["lower_wick_pct"] <= ELEPHANT_MAX_WICK_PCT
            and a["upper_wick_pct"] + a["lower_wick_pct"] <= ELEPHANT_MAX_TOTAL_WICK_PCT
        )
        detail["body_vs_avg"] = round(a["body"] / avg_body, 2) if avg_body > 0 else None
        last20 = prior[-20:]
        detail["body_rank_20"] = round(sum(1 for b in last20 if anatomy(b)["body"] < a["body"]) / len(last20), 2)
        if avg_body > 0 and a["body"] >= ELEPHANT_BODY_MULT * avg_body and wick_ok and a["color"] != "doji":
            events.append("bull_elephant" if a["bullish"] else "bear_elephant")
            cleared = 0
            for b in reversed(prior):
                if (a["bullish"] and bar["c"] > b["h"]) or (a["bearish"] and bar["c"] < b["l"]):
                    cleared += 1
                else:
                    break
            detail["bars_cleared"] = cleared
            detail["elephant_origin"] = _elephant_origin(bar, a, prior)

    if prior:
        prev = prior[-1]
        pa = anatomy(prev)
        # A 180 is two solid, comparable bars: a sliver followed by a big bar is
        # an elephant, not a 180.
        comparable = pa["body"] > 0 and a["body"] > 0 and 0.5 <= a["body"] / pa["body"] <= 2.0
        if comparable and pa["body_pct"] >= 0.5 and a["body_pct"] >= 0.5:
            if pa["bearish"] and a["bullish"]:
                recovery = (bar["c"] - prev["c"]) / (prev["o"] - prev["c"])
                if recovery >= ONE_EIGHTY_RECOVER_PCT:
                    events.append("bull_180")
                    detail["recovery_pct"] = round(recovery, 2)
            if pa["bullish"] and a["bearish"]:
                recovery = (prev["c"] - bar["c"]) / (prev["c"] - prev["o"])
                if recovery >= ONE_EIGHTY_RECOVER_PCT:
                    events.append("bear_180")
                    detail["recovery_pct"] = round(recovery, 2)
        if pa["color"] != a["color"] and "doji" not in (pa["color"], a["color"]):
            events.append("color_change")

    if len(prior) >= NRB_LOOKBACK:
        ranges = [b["h"] - b["l"] for b in prior[-NRB_LOOKBACK:]]
        avg_range = sum(ranges) / len(ranges)
        if avg_range > 0 and a["range"] <= NRB_RANGE_MULT * avg_range:
            events.append("narrow_range_bar")

    if len(prior) >= 2:
        control, ignored = prior[-2], prior[-1]
        ca, ia = anatomy(control), anatomy(ignored)
        small = ca["body"] > 0 and ia["body"] <= 0.5 * ca["body"]
        if ca["bullish"] and ia["bearish"] and a["bullish"] and small and bar["c"] > ignored["h"] and ignored["l"] >= control["l"]:
            events.append("red_bar_ignored")
        if ca["bearish"] and ia["bullish"] and a["bearish"] and small and bar["c"] < ignored["l"] and ignored["h"] <= control["h"]:
            events.append("green_bar_ignored")

    return {
        "anatomy": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in a.items()},
        "events": events,
        "detail": detail,
        "bias": _event_bias(events),
    }


def _elephant_origin(bar: dict[str, Any], a: dict[str, Any], prior: list[dict[str, Any]]) -> str:
    """Igniting (starts at the 20), continuation, or exhausting (starts far from the 20 after a run)."""
    closes = [b["c"] for b in prior]
    sma20 = sma(closes, SMA_FAST)
    if sma20 is None:
        return "unknown"
    band = 0.5 * (atr(prior) or abs(sma20) * NEAR_SMA_PCT)
    if bar["l"] <= sma20 <= bar["h"] or abs(bar["o"] - sma20) <= band:
        return "igniting"
    run = prior[-3:]
    rallied = len(run) == 3 and all(run[i]["c"] > run[i - 1]["c"] for i in (1, 2))
    declined = len(run) == 3 and all(run[i]["c"] < run[i - 1]["c"] for i in (1, 2))
    if (a["bullish"] and bar["o"] > sma20 and rallied) or (a["bearish"] and bar["o"] < sma20 and declined):
        return "exhausting"
    return "continuation"


def _event_bias(events: list[str]) -> str:
    bull = {"bottoming_tail", "bull_elephant", "bull_180", "red_bar_ignored"}
    bear = {"topping_tail", "bear_elephant", "bear_180", "green_bar_ignored"}
    b, s = bool(bull & set(events)), bool(bear & set(events))
    return "bullish" if b and not s else "bearish" if s and not b else "neutral"


# ── Market state: the 20, the 200, and where price sits ──

def market_state(
    bars: list[dict[str, Any]],
    prior_close: Optional[float] = None,
    fab4_bars: int = FAB4_RANGE_BARS,
) -> dict[str, Any]:
    if not bars:
        raise ValueError("market_state needs at least one bar")
    closes = [b["c"] for b in bars]
    last = bars[-1]
    price = last["c"]
    atr_value = atr(bars)
    sma20 = sma(closes, SMA_FAST)
    sma200 = sma(closes, SMA_SLOW)
    slope20 = _slope_label(sma20, sma(closes, SMA_FAST, SLOPE_LOOKBACK), atr_value)
    slope200 = _slope_label(sma200, sma(closes, SMA_SLOW, SLOPE_LOOKBACK), atr_value)
    warnings: list[str] = []
    if sma20 is None:
        warnings.append(f"Need {SMA_FAST}+ bars for the 20 SMA; nothing here is tradeable yet.")
    if sma200 is None:
        warnings.append(f"Only {len(bars)} bars: the 200 SMA (the veto) is unavailable. Send {SMA_SLOW}+ bars.")

    def near(level: Optional[float]) -> bool:
        if level is None:
            return False
        pct_ok = abs(price - level) / max(price, 1e-9) <= NEAR_SMA_PCT
        atr_ok = atr_value is not None and abs(price - level) <= NEAR_SMA_ATR_MULT * atr_value
        return pct_ok or atr_ok or last["l"] <= level <= last["h"]

    extended = None
    if sma20 is not None:
        dist = price - sma20
        if abs(dist) / max(sma20, 1e-9) >= EXTENDED_SMA_PCT or (atr_value and abs(dist) >= EXTENDED_SMA_ATR_MULT * atr_value):
            extended = "above" if dist > 0 else "below"

    # Trend: price, 20 and 200 stacked, with the 20 sloping the same way.
    trend = "mixed"
    if sma20 is not None:
        stacked_up = price > sma20 and (sma200 is None or sma20 > sma200)
        stacked_down = price < sma20 and (sma200 is None or sma20 < sma200)
        if stacked_up and slope20 == "rising":
            trend = "bullish"
        elif stacked_down and slope20 == "falling":
            trend = "bearish"

    # The 200 is the veto: it removes trades, it never creates them.
    long_veto = short_veto = False
    if sma200 is not None:
        long_veto = price < sma200 and slope200 != "rising"
        short_veto = price > sma200 and slope200 != "falling"

    # Market state: narrow (the coil) / trending (the move) / wide (the climax).
    slant = _slant(closes, atr_value)
    state = None
    spread_pct = None
    if sma20 is not None and sma200 is not None:
        spread_pct = abs(sma20 - sma200) / max(price, 1e-9)
        state = _classify_state(spread_pct, slant)

    # Fab 4 trap zone: the box around 20, 200, prior close and the recent range.
    if prior_close is None:
        prior_close = _derive_prior_close(bars)
    # The recent range is one of the four items; exclude the current bar so a
    # breakout bar does not drag the box along with it.
    base = bars[-fab4_bars - 1:-1] or bars[-1:]
    box_items = [x for x in (sma20, sma200, prior_close) if x is not None]
    box_high = max(box_items + [max(b["h"] for b in base)])
    box_low = min(box_items + [min(b["l"] for b in base)])
    territory = "green_territory" if price > box_high else "red_territory" if price < box_low else "trap_zone"

    locations = []
    if near(sma20):
        locations.append("near_20")
    if extended:
        locations.append(f"extended_{extended}_20")
    if near(sma200):
        locations.append("near_200")

    playbook_hint = _state_hint(state, trend, territory, extended)
    state_rule = MARKET_STATES.get(state or "", {}).get("velez_action_rule")
    return {
        "price": price,
        "sma20": _r(sma20), "sma200": _r(sma200), "atr": _r(atr_value),
        "sma20_slope": slope20, "sma200_slope": slope200,
        "trend": trend,
        "veto_200": {"longs_vetoed": long_veto, "shorts_vetoed": short_veto},
        "state": state, "state_rule": state_rule, "sma_spread_pct": _r(spread_pct, 5),
        "sma20_slant": slant,
        "location": locations,
        "extended_from_20": extended,
        "distance_to_20_atr": _r((price - sma20) / atr_value) if sma20 is not None and atr_value else None,
        "fab4": {
            "prior_close": _r(prior_close), "box_high": _r(box_high), "box_low": _r(box_low),
            "territory": territory,
        },
        "playbook_hint": playbook_hint,
        "bars": len(bars),
        "warnings": warnings,
    }


def _slant(closes: list[float], atr_value: Optional[float]) -> dict[str, Any]:
    return slant_from_smas(
        sma(closes, SMA_FAST), sma(closes, SMA_FAST, SLOPE_LOOKBACK), sma(closes, SMA_FAST, 2 * SLOPE_LOOKBACK), atr_value
    )


def slant_from_smas(
    now: Optional[float], mid: Optional[float], old: Optional[float], atr_value: Optional[float]
) -> dict[str, Any]:
    """Slant of the 20 from its value now, one lookback ago and two lookbacks ago (ATR per bar)."""
    if now is None or mid is None or not atr_value:
        return {"label": None, "atr_per_bar": None, "accelerating": None}
    per_bar = (now - mid) / (SLOPE_LOOKBACK * atr_value)
    prior = (mid - old) / (SLOPE_LOOKBACK * atr_value) if old is not None else None
    accelerating = (
        prior is not None
        and abs(per_bar) >= SLANT_STEEP_ATR_PER_BAR / 2
        and (prior == 0 or (per_bar / prior) >= SLANT_ACCEL_RATIO)
    )
    if abs(per_bar) < SLANT_FLAT_ATR_PER_BAR:
        label = "flat"
    elif abs(per_bar) >= SLANT_STEEP_ATR_PER_BAR or accelerating:
        label = "steep"
    else:
        label = "steady"
    return {"label": label, "atr_per_bar": round(per_bar, 4), "accelerating": bool(accelerating)}


def classify_state(
    spread_pct: float,
    slant: dict[str, Any],
    narrow_pct: float = NARROW_STATE_PCT,
    wide_pct: float = WIDE_STATE_PCT,
) -> str:
    """Narrow = pinched 20/200. Wide = max gap, or a steep/curving 20 off a real gap. Trending = the ramp between.

    The gap thresholds are timeframe-dependent (a daily chart's 20/200 sit much
    further apart than a 2-minute chart's), so each bot passes its own.
    """
    if spread_pct <= narrow_pct:
        return "narrow"
    if spread_pct >= wide_pct or slant["label"] == "steep":
        return "wide"
    if slant["label"] == "steady":
        return "trending"
    return "transition"


_classify_state = classify_state


def play_family(play: str, metadata: Optional[dict[str, Any]] = None) -> str:
    """continuation or reversal. A play can declare itself (e.g. a tail at a rising 20 is continuation)."""
    declared = str((metadata or {}).get("setup_family") or "").lower()
    if declared in ("continuation", "reversal"):
        return declared
    return "reversal" if str(play).lower() in REVERSAL_PLAYS else "continuation"


def entry_gate(
    side: str,
    play: str,
    *,
    price: float,
    sma200: Optional[float],
    sma200_slope: Optional[str],
    state: Optional[str],
    near_200: bool,
    elephant_origin: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    extension_atr: Optional[float] = None,
    extension_side: Optional[str] = None,
    decision_time: Optional[datetime] = None,
    market_bias: Optional[str] = None,
) -> dict[str, Any]:
    """The hard Velez rules every bot applies before an entry. Returns {allowed, reasons, family}.

    With `extension_atr`/`extension_side` (price vs the 20 SMA in ATRs), two
    more rules apply: no chasing a three-finger spread in the trend's
    direction, and adds (color_change_add) only early in the move (P1/P2).

    With `decision_time` (when the entry would be taken; US equities only) the
    session windows apply: no new entries in the first 15 minutes (5 for gap
    plays), no trend entries in the midday chop, none in the last 15 minutes.

    With `market_bias` ("long"/"short"/"none" from market_bias()), trade with
    the market: no trend entries against it or when it has no side, and no
    reversal against it unless the stock is at its 200.
    """
    long = _norm_side(side) == "long"
    family = play_family(play, metadata)
    reasons: list[str] = []
    if extension_atr is not None and family == "continuation":
        tfs = three_finger_spread("long" if long else "short", extension_atr, extension_side or "at")
        if tfs["status"] == "block":
            reasons.append("three_finger_spread_chase")
    # A caller that measures the extension (side given) opts in to the add rule: an add whose
    # trend position can't be read (no 20 SMA / ATR yet) is not a verified P1/P2 add.
    if extension_side is not None and str(play).lower() == "color_change_add" and not add_allowed(trend_position(extension_atr)):
        reasons.append("add_outside_p1_p2")
    if sma200 is not None:
        vetoed = (price < sma200 and sma200_slope != "rising") if long else (price > sma200 and sma200_slope != "falling")
        if vetoed and not (family == "reversal" and near_200):
            reasons.append("veto_200")
    if state == "wide" and family == "continuation":
        reasons.append("wide_state_no_trend_entry")
    if elephant_origin == "exhausting":
        reasons.append("exhausting_elephant")
    if decision_time is not None:
        window = session_window(decision_time, play, family)
        if not window["allow"]:
            reasons.append(window["reason"])
    if market_bias is not None and market_bias != "unknown":
        wanted = "long" if long else "short"
        if market_bias not in ("long", "short"):
            if family == "continuation":
                reasons.append("market_no_side")
        elif market_bias != wanted and not (family == "reversal" and near_200):
            reasons.append("against_market")
    return {"allowed": not reasons, "reasons": reasons, "family": family}


# ── Rules ported from Trading Bull Academy (src/strategy/*.ts) ──

def extension_atr(price: float, sma20: Optional[float], atr_value: Optional[float]) -> tuple[Optional[float], str]:
    """Distance of price from the 20 SMA in ATRs, and which side it is on."""
    if sma20 is None or not atr_value:
        return None, "at"
    side = "above" if price > sma20 else "below" if price < sma20 else "at"
    return round(abs(price - sma20) / atr_value, 2), side


def three_finger_spread(
    direction: str,
    extension: Optional[float],
    side: str,
    family: str = "continuation",
    reversal_event: bool = False,
) -> dict[str, Any]:
    """Velez's three-finger spread -- price stretched far from the 20.

    Measured in ATRs (the rule is visual, so it scales with the chart). It
    blocks CHASING in the stretch's direction and is the PERMISSION for V-top
    / V-bottom reversals against it, which also need a strong event bar.
    """
    if extension is None:
        return {"status": "ok", "reason": "No 20 SMA/ATR read; spread not evaluated."}
    long = _norm_side(direction) == "long"
    with_stretch = (long and side == "above") or (not long and side == "below")
    against = (long and side == "below") or (not long and side == "above")
    if family == "reversal":
        if not against or extension < TFS_CAUTION_ATR:
            return {"status": "caution", "reason": f"Reversal without a three-finger spread ({extension} ATR). Velez plays V tops/bottoms only off a spread."}
        if not reversal_event:
            return {"status": "caution", "reason": "Spread present but no confirmed reversal event bar yet."}
        return {"status": "ok", "reason": f"Three-finger spread ({extension} ATR) qualifies the reversal."}
    if with_stretch and extension >= TFS_BLOCK_ATR:
        return {"status": "block", "reason": f"{extension} ATR from the 20 in the trade's direction: that's a chase."}
    if with_stretch and extension >= TFS_CAUTION_ATR:
        return {"status": "caution", "reason": f"Stretched {extension} ATR from the 20; wait for a pullback toward it."}
    return {"status": "ok", "reason": "Not stretched in the trade's direction."}


def trend_position(extension: Optional[float], breakout: bool = False, follow_through: bool = True) -> str:
    """Where in the move price is: P1 fresh, P2 established, P3 late, P4 extended (distance from the 20 in ATRs)."""
    if extension is None:
        return "unknown"
    if breakout and follow_through and extension < 1:
        return "P1"
    if follow_through and extension < TFS_CAUTION_ATR:
        return "P2"
    if extension < TFS_BLOCK_ATR:
        return "P3"
    return "P4"


def add_allowed(position: str) -> bool:
    """Velez adds to winners early in the move only: P1/P2. Never late (P3) or extended (P4)."""
    return position in ("P1", "P2")


def first_color_change(bars: list[dict[str, Any]], direction: str, min_push: int = 2) -> bool:
    """The FIRST small counter-color rest bar of the move (the RBI/GBI add point).

    Needs >= `min_push` bars of push, a counter bar no bigger than half the
    push bodies, holding inside the push, and no earlier counter-color bar
    since the move began (where price last closed on the other side of the 20).
    The counter bar may be the last bar or the one before a resuming bar.
    """
    long = _norm_side(direction) == "long"
    is_with = (lambda b: b["c"] > b["o"]) if long else (lambda b: b["c"] < b["o"])
    is_counter = (lambda b: b["c"] < b["o"]) if long else (lambda b: b["c"] > b["o"])
    closes = [b["c"] for b in bars]
    for idx in (len(bars) - 1, len(bars) - 2):
        if idx < min_push or not is_counter(bars[idx]):
            continue
        push, i = 0, idx - 1
        while i >= 0 and is_with(bars[i]):
            push += 1
            i -= 1
        if push < min_push:
            continue
        push_bodies = [abs(b["c"] - b["o"]) for b in bars[idx - push: idx]]
        avg_push = sum(push_bodies) / len(push_bodies)
        counter = bars[idx]
        small = abs(counter["c"] - counter["o"]) <= 0.5 * avg_push
        last_push = bars[idx - 1]
        holds = (counter["l"] >= min(last_push["o"], last_push["c"]) - avg_push) if long else (
            counter["h"] <= max(last_push["o"], last_push["c"]) + avg_push
        )
        no_second = all(not is_counter(b) for b in bars[idx + 1:])
        move_start = -1
        for j in range(idx - 1, SMA_FAST - 2, -1):
            line = sma(closes[: j + 1], SMA_FAST)
            if line is None:
                break
            if (long and closes[j] < line) or (not long and closes[j] > line):
                move_start = j
                break
        # No close on the other side of the 20 in view: the whole history is the move.
        first_in_move = all(not is_counter(b) for b in bars[move_start + 1: idx])
        if small and holds and no_second and first_in_move:
            return True
    return False


def trifecta(bars15: list[dict[str, Any]], bars5: list[dict[str, Any]], bars2: list[dict[str, Any]]) -> dict[str, Any]:
    """Velez's 2/5/15 alignment: 15m sets the side, 5m sets up, 2m triggers."""
    reasons: list[str] = []
    c15 = [b["c"] for b in bars15]
    s_now, s_prev = sma(c15, SMA_FAST), sma(c15, SMA_FAST, 1)
    if s_now is None or s_prev is None:
        return {"status": "BLOCK", "bias": "unknown", "reasons": ["Need 21+ 15m bars for the 15m 20 SMA."]}
    last15 = bars15[-1]["c"]
    bias = "bullish" if last15 > s_now and s_now >= s_prev else "bearish" if last15 < s_now and s_now <= s_prev else "neutral"
    if bias == "neutral":
        return {"status": "BLOCK", "bias": bias, "reasons": ["15m bias is neutral: no side."]}
    if len(bars5) < 20 or len(bars2) < 2:
        return {"status": "BLOCK", "bias": bias, "reasons": ["Need 20+ 5m bars and 2+ 2m bars."]}
    window = bars5[-20:-3]
    hi, lo = max(b["h"] for b in window), min(b["l"] for b in window)
    last5 = bars5[-1]["c"]
    breakout = last5 > hi if bias == "bullish" else last5 < lo
    near = abs(last5 - (hi if bias == "bullish" else lo)) / max(abs(hi), 1e-9) < 0.003
    setup = "aligned" if breakout else "mixed" if near else "invalid"
    prev2, last2 = bars2[-2], bars2[-1]
    trigger = (last2["c"] > prev2["h"]) if bias == "bullish" else (last2["c"] < prev2["l"])
    if setup == "invalid":
        return {"status": "BLOCK", "bias": bias, "setup": setup, "trigger": trigger, "reasons": ["5m setup is invalid (no range break)."]}
    if setup == "mixed" or not trigger:
        reasons.append("Partial 2/5/15 alignment; caution only.")
        return {"status": "CAUTION", "bias": bias, "setup": setup, "trigger": trigger, "reasons": reasons}
    return {"status": "PASS", "bias": bias, "setup": setup, "trigger": trigger, "reasons": ["2/5/15 alignment confirmed."]}


def ma20_reclaim_quality(bars: list[dict[str, Any]], direction: str) -> dict[str, Any]:
    """Quality of the latest 20 SMA reclaim: FIRST_CLEAN_RECLAIM, RETEST_HOLD, LATE_RECLAIM or FAILED_RETEST."""
    long = _norm_side(direction) == "long"
    closes = [b["c"] for b in bars]
    line = [sma(closes[: i + 1], SMA_FAST) for i in range(len(closes))]
    last = len(closes) - 1
    reclaim = -1
    for i in range(last, 0, -1):
        if line[i - 1] is None or line[i] is None:
            continue
        crossed = (closes[i - 1] <= line[i - 1] and closes[i] > line[i]) if long else (closes[i - 1] >= line[i - 1] and closes[i] < line[i])
        if crossed:
            reclaim = i
            break
    if last < 0 or line[last] is None:
        return {"state": "LATE_RECLAIM", "bars_since": None, "held": False}
    on_side = closes[last] > line[last] if long else closes[last] < line[last]
    if reclaim == -1:
        return {"state": "LATE_RECLAIM" if on_side else "FAILED_RETEST", "bars_since": None, "held": False}
    held = all(
        (closes[i] > line[i]) if long else (closes[i] < line[i])
        for i in range(reclaim, last + 1) if line[i] is not None
    )
    since = last - reclaim
    # A retest means a post-reclaim bar came back to (or within a quarter ATR of) the 20.
    tolerance = 0.25 * (atr(bars) or 0.0)
    retested = any(
        (bars[i]["l"] <= line[i] + tolerance) if long else (bars[i]["h"] >= line[i] - tolerance)
        for i in range(reclaim + 1, last + 1) if line[i] is not None
    )
    if not held:
        state = "FAILED_RETEST"
    elif since <= 2:
        state = "FIRST_CLEAN_RECLAIM"
    elif since <= 8 and retested:
        state = "RETEST_HOLD"
    else:
        state = "LATE_RECLAIM"
    return {"state": state, "bars_since": since, "held": held, "retested": retested}


def gap_open_check(
    gap_pct: float,
    minutes_since_open: float,
    reclaim_or_hold: bool,
    chase_from_open_pct: float,
) -> dict[str, Any]:
    """Gap-at-open discipline: a real gap, wait for the opening range, a reclaim/hold, and no chasing the open."""
    if abs(gap_pct) < 1.0:
        return {"status": "NOT_APPLICABLE", "reason": "Gap under 1%: no gap edge."}
    if minutes_since_open < 5:
        return {"status": "BLOCK", "reason": "Wait for the opening range (at least the first 5 minutes / first 2-minute bars)."}
    if not reclaim_or_hold:
        return {"status": "BLOCK", "reason": "No reclaim/hold confirmation for the gap."}
    if chase_from_open_pct > 2.5:
        return {"status": "BLOCK", "reason": "More than 2.5% from the open: that's a chase."}
    if chase_from_open_pct > 1.5:
        return {"status": "CAUTION", "reason": "Extended from the open; tight execution only."}
    return {"status": "PASS", "reason": "Opening range respected, reclaim/hold confirmed, no chase."}


PULLBACK_SCALP_STARTER_FRACTION = 0.25

EIGHT_STEPS = (
    "market_context", "qualified_setup", "trigger", "initial_stop",
    "position_size", "trail_plan", "exit_and_review", "add_on_plan",
)


def eight_step_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Every trade needs all eight steps written down before entry (the add-on plan may follow for a first entry)."""
    missing = [step for step in EIGHT_STEPS[:-1] if not plan.get(step)]
    if missing:
        return {"status": "BLOCK", "missing": missing}
    if not plan.get("add_on_plan"):
        return {"status": "CAUTION", "missing": ["add_on_plan"]}
    return {"status": "PASS", "missing": []}


def _derive_prior_close(bars: list[dict[str, Any]]) -> Optional[float]:
    last_ts = _local(bars[-1]["t"])
    if last_ts is None:
        return None
    for b in reversed(bars):
        ts = _local(b["t"])
        if ts is not None and ts.date() < last_ts.date():
            return b["c"]
    return None


def _state_hint(state: Optional[str], trend: str, territory: str, extended: Optional[str]) -> str:
    if territory == "trap_zone":
        return "Inside the Fab 4 trap zone: no-man's land. Do less; wait for price to leave the box."
    if state == "narrow":
        return "Narrow state (the coil): 20 and 200 pinched and flat. Play the explosion out of it — elephant bars in the direction price leaves the box."
    if state == "wide":
        side = f" and extended {extended} the 20" if extended else ""
        return (
            f"Wide state (the climax){side}: do NOT buy/short the trend. Take profits, or fade/reverse with tails, 180s "
            "and failed new highs/lows."
        )
    if state == "trending" and trend in ("bullish", "bearish"):
        verb = "buy" if trend == "bullish" else "short"
        return f"Trending state (the move): 20 ramping steadily. {verb.capitalize()} the color changes at or near the 20 (RBI/GBI, buy/sell setup)."
    if state == "transition":
        return "Transition: the 20 and 200 are apart but the 20 is flat — no coil and no move. Do less."
    if trend == "bullish":
        return "Bullish stack with a rising 20: buy pullbacks to the 20 (buy setup, RBI, bottoming tail, NRB)."
    if trend == "bearish":
        return "Bearish stack with a falling 20: short rallies into the 20 (sell setup, GBI, topping tail, NRB)."
    return "Mixed structure: no clear side. Smallest size or no trade."


def _r(value: Optional[float], digits: int = 4) -> Optional[float]:
    return round(value, digits) if value is not None else None


# ── Checklist: would Velez take this? ──

def checklist(
    bars: list[dict[str, Any]],
    side: str,
    play: str = "",
    prior_close: Optional[float] = None,
    tick: float = 0.01,
    market_bias: Optional[str] = None,
) -> dict[str, Any]:
    """Grade an idea on the last bar. `market_bias` ("long"/"short"/"none" from
    market_bias()) adds the trade-with-the-market check the bots enforce."""
    side = _norm_side(side)
    if len(bars) < 2:
        raise ValueError("checklist needs the event bar plus history")
    ms = market_state(bars, prior_close)
    event = classify_candle(bars[-1], bars[:-1])
    events = set(event["events"])
    play = (play or "").strip().lower()
    family = _play_family(play, events, ms, side)
    long = side == "long"

    checks: list[dict[str, Any]] = []

    def add(name: str, passed: Optional[bool], required: bool, detail: str) -> None:
        checks.append({"check": name, "passed": passed, "required": required, "detail": detail})

    veto = ms["veto_200"]["longs_vetoed" if long else "shorts_vetoed"]
    at_200_exception = "near_200" in ms["location"] and family == "reversal"
    add("200_veto", not veto or at_200_exception, True,
        "The 200 is the veto." + (" Price is on the wrong side of a non-supportive 200." if veto else " Not vetoed.")
        + (" Exception: reversal play at the 200 itself." if veto and at_200_exception else ""))

    if family == "continuation":
        aligned = ms["sma20_slope"] == ("rising" if long else "falling")
        add("20_slope_with_trade", aligned, True, f"20 SMA is {ms['sma20_slope']}; continuation trades go with its slope.")
        good_loc = "near_20" in ms["location"] or "near_200" in ms["location"] or ms["fab4"]["territory"] == ("green_territory" if long else "red_territory")
        add("location", good_loc, True, "Continuation entries belong at the 20/200 or on a break out of the trap zone, not in the middle of nowhere.")
        exhausting = event["detail"].get("elephant_origin") == "exhausting"
        add("not_exhaustion", not exhausting, True, "Exhausting elephants (born far from the 20 after a run) are where you take profits, not where you enter.")
        add("not_wide_state", ms["state"] != "wide", True,
            "Wide state (the climax): do not buy/short the trend." if ms["state"] == "wide" else f"State is {ms['state']}, not the climax.")
        explosion = bool(events & {"bull_elephant", "bear_elephant"}) or ms["fab4"]["territory"] != "trap_zone"
        fits = (
            (ms["state"] == "narrow" and explosion)
            or (ms["state"] == "trending" and ("near_20" in ms["location"] or bool(events & {"color_change", "red_bar_ignored", "green_bar_ignored"})))
            or ms["state"] is None
        )
        add("play_fits_state", fits, False,
            {"narrow": "Narrow state: the play is the explosion out of the coil (elephant / box break).",
             "trending": "Trending state: the play is a color change at or near the 20.",
             "transition": "Transition state (flat 20, no coil): nothing fits cleanly — do less.",
             "wide": "Wide state (the climax): no trend entry fits."}.get(ms["state"] or "", "No 200 yet; state unknown."))
    else:
        stretched = ms["extended_from_20"] == ("below" if long else "above") or "near_200" in ms["location"]
        add("location", stretched, True, "Reversals need price stretched away from the 20 (or testing the 200). A reversal at the 20 is just noise.")
        add("wide_state", ms["state"] in ("wide", None), False, f"Fades/reversals belong in the wide state, the climax (state={ms['state']}).")

    want_bull = {"bottoming_tail", "bull_elephant", "bull_180", "red_bar_ignored"}
    want_bear = {"topping_tail", "bear_elephant", "bear_180", "green_bar_ignored"}
    matched = sorted(events & (want_bull if long else want_bear))
    if family == "continuation" and not matched:
        prev = bars[-2]
        if (long and bars[-1]["c"] > prev["h"] and bars[-1]["c"] > bars[-1]["o"]) or (
            not long and bars[-1]["c"] < prev["l"] and bars[-1]["c"] < bars[-1]["o"]
        ):
            matched = ["pullback_break_of_prior_bar"]
    add("event_bar", bool(matched), True,
        f"Event bar prints {matched}." if matched else f"Last bar prints {sorted(events) or 'nothing'}; no {'bullish' if long else 'bearish'} Velez event to act on.")

    add("not_in_trap_zone", ms["fab4"]["territory"] != "trap_zone" or family == "reversal", False,
        f"Fab 4 territory: {ms['fab4']['territory']}.")

    # Three-finger spread, measured where the setup starts (the event bar's open)
    # so an igniting elephant's own body never makes it look like a chase.
    ext, ext_side = extension_atr(bars[-1]["o"], ms["sma20"], ms["atr"])
    reversal_event = bool(events & ({"bottoming_tail", "bull_180", "bull_elephant"} if long else {"topping_tail", "bear_180", "bear_elephant"}))
    tfs = three_finger_spread(side, ext, ext_side, family, reversal_event)
    if family == "continuation":
        add("three_finger_spread", tfs["status"] != "block", True, tfs["reason"])
        if tfs["status"] == "caution":
            add("not_stretched", False, False, tfs["reason"])
    else:
        add("spread_qualifies_reversal", tfs["status"] == "ok", False, tfs["reason"])
    position = trend_position(ext, breakout=bool(matched), follow_through=family == "continuation")

    # Session windows: the same rule the bots enforce (a failure here is a no-trade),
    # read at the entry decision time (the event bar's close); daily+ bars have none.
    window = session_window(decision_time(bars), play, family)
    if window["window"] != "unknown":
        details = {
            "opening_range_wait": "Amateur hour: let the first 15 minutes settle (5 for gap plays) before a new entry.",
            "midday_chop": "The midday chop (11:30–13:30 ET): no trend entries.",
            "too_late_in_session": "Last 15 minutes: no new entries into the close.",
        }
        if window["window"] == "extended_hours":
            add("time_of_day", False, False, "Outside regular hours: thin liquidity, smaller or no trades.")
        else:
            add("time_of_day", window["allow"], True,
                details.get(window["reason"], f"{window['window'].replace('_', ' ')} window: new entries allowed."))

    if market_bias is not None and market_bias != "unknown":
        wanted = "long" if long else "short"
        if market_bias in ("long", "short"):
            ok = market_bias == wanted or (family == "reversal" and "near_200" in ms["location"])
            add("with_the_market", ok, True,
                f"SPY/QQQ lean {market_bias}." + ("" if ok else " Don't fight the market: trend entries go with it; reversals against it only at the 200."))
        else:
            add("with_the_market", family == "reversal", True,
                "SPY/QQQ have no side: no trend entries." if family == "continuation" else "SPY/QQQ have no side; a reversal may still trade.")

    plan = trade_plan(side, bars[-1]["h"], bars[-1]["l"], tick=tick)
    room = _room(bars[:-1], side, plan["entry"], plan["risk_per_share"])
    if room is not None:
        add("room_to_run", room["r_to_obstacle"] >= 1.0, False,
            f"Nearest obstacle {room['obstacle']} is {room['r_to_obstacle']}R away (want ≥1R, ideally 2R).")

    required_fail = [c for c in checks if c["required"] and not c["passed"]]
    optional_fail = [c for c in checks if not c["required"] and c["passed"] is False]
    if required_fail:
        grade, verdict = "F", "pass"
    elif not optional_fail:
        grade, verdict = "A", "take_full"
    elif len(optional_fail) == 1:
        grade, verdict = "B", "take_starter_lot"
    else:
        grade, verdict = "C", "pass"
    return {
        "side": side, "play": play or None, "play_family": family,
        "grade": grade, "verdict": verdict,
        "checks": checks,
        "failed_required": [c["check"] for c in required_fail],
        "event": event, "market_state": ms, "plan": plan,
        "extension_atr": ext, "extension_side": ext_side,
        "three_finger_spread": tfs["status"],
        "trend_position": position, "add_allowed": add_allowed(position),
        "first_color_change": first_color_change(bars, side),
    }


def _play_family(play: str, events: set[str], ms: dict[str, Any], side: str) -> str:
    if play in REVERSAL_PLAYS:
        return "reversal"
    if play in CONTINUATION_PLAYS:
        return "continuation"
    # Infer: a tail or 180 printed while stretched from the 20 is a reversal.
    stretched = ms["extended_from_20"] == ("below" if side == "long" else "above")
    if stretched and events & {"bottoming_tail", "topping_tail", "bull_180", "bear_180"}:
        return "reversal"
    return "continuation"


def session_window(ts: Optional[datetime], play: str = "", family: Optional[str] = None) -> dict[str, Any]:
    """Whether a NEW entry may be taken at `ts` (the entry decision time, ET).

    Regular hours only; outside them no session rule is applied (the caller
    decides whether it trades extended hours at all).
    """
    local = _local(ts)
    if local is None:
        return {"window": "unknown", "allow": True, "reason": None}
    fam = family or play_family(play)
    t = local.time()
    if t < SESSION_OPEN or t > SESSION_CLOSE:
        return {"window": "extended_hours", "allow": True, "reason": None}
    minutes = (local.hour * 60 + local.minute) - (SESSION_OPEN.hour * 60 + SESSION_OPEN.minute)
    wait = GAP_OPENING_WAIT_MIN if str(play).lower() in GAP_PLAYS else OPENING_WAIT_MIN
    if minutes < wait:
        return {"window": "opening", "allow": False, "reason": "opening_range_wait"}
    if t >= LAST_ENTRY:
        return {"window": "closing", "allow": False, "reason": "too_late_in_session"}
    if MIDDAY_START <= t < MIDDAY_END:
        if fam == "continuation":
            return {"window": "midday", "allow": False, "reason": "midday_chop"}
        return {"window": "midday", "allow": True, "reason": None}
    if t >= time(15, 0):
        return {"window": "power_hour", "allow": True, "reason": None}
    return {"window": "prime", "allow": True, "reason": None}


def decision_time(bars: list[dict[str, Any]]) -> Optional[datetime]:
    """When an entry off the last bar is taken: its close (start + bar spacing).

    None for daily or longer bars (session windows are intraday) or when the
    bar timestamps can't say.
    """
    stamps = [b.get("t") for b in bars[-6:] if b.get("t") is not None]
    try:
        gaps = [(b - a).total_seconds() / 60 for a, b in zip(stamps, stamps[1:]) if (b - a).total_seconds() > 0]
    except TypeError:
        return None
    if not gaps or min(gaps) >= 390:
        return None
    return bars[-1]["t"] + timedelta(minutes=min(gaps))


def index_bias(bars: list[dict[str, Any]]) -> str:
    """One index's side: above a rising 20 = bullish, below a falling 20 = bearish, else neutral."""
    closes = [b["c"] for b in bars]
    now, prev = sma(closes, SMA_FAST), sma(closes, SMA_FAST, SLOPE_LOOKBACK)
    if now is None or prev is None:
        return "unknown"
    last = closes[-1]
    if last > now and now > prev:
        return "bullish"
    if last < now and now < prev:
        return "bearish"
    return "neutral"


def market_bias(*index_bars: list[dict[str, Any]]) -> dict[str, Any]:
    """Trade with the market (SPY/QQQ). long = at least one index bullish and none bearish;
    short = the mirror; none = the indexes disagree or are all neutral; unknown = no data."""
    reads = [index_bias(bars) for bars in index_bars if bars]
    known = [r for r in reads if r != "unknown"]
    if not known:
        side = "unknown"
    elif "bullish" in known and "bearish" not in known:
        side = "long"
    elif "bearish" in known and "bullish" not in known:
        side = "short"
    else:
        side = "none"
    return {"bias": side, "indexes": reads}


def _room(prior: list[dict[str, Any]], side: str, entry: float, risk: float) -> Optional[dict[str, Any]]:
    if not prior or risk <= 0:
        return None
    window = prior[-60:]
    if side == "long":
        above = [b["h"] for b in window if b["h"] > entry]
        if not above:
            return {"obstacle": None, "r_to_obstacle": 99.0}
        obstacle = min(above)
        return {"obstacle": _r(obstacle), "r_to_obstacle": round((obstacle - entry) / risk, 2)}
    below = [b["l"] for b in window if b["l"] < entry]
    if not below:
        return {"obstacle": None, "r_to_obstacle": 99.0}
    obstacle = max(below)
    return {"obstacle": _r(obstacle), "r_to_obstacle": round((entry - obstacle) / risk, 2)}


def _norm_side(side: str) -> str:
    s = str(side).strip().lower()
    if s in ("long", "buy", "bull", "bullish"):
        return "long"
    if s in ("short", "sell", "bear", "bearish"):
        return "short"
    raise ValueError(f"side must be long or short, got {side!r}")


# ── Trade plan: entry, event stop, MLPT, lots, targets ──

def trade_plan(
    side: str,
    event_high: float,
    event_low: float,
    entry: Optional[float] = None,
    tick: float = 0.01,
    account_equity: Optional[float] = None,
    risk_pct: float = 0.01,
    max_loss_per_trade: Optional[float] = None,
    lots: int = 3,
    aggressive_entry: bool = False,
    pullback_scalp: bool = False,
) -> dict[str, Any]:
    side = _norm_side(side)
    long = side == "long"
    if event_high < event_low:
        raise ValueError("event_high must be ≥ event_low")
    lots = max(1, int(lots))
    midpoint = (event_high + event_low) / 2.0
    if entry is None:
        # Velez: act on the break of the event bar, not before it.
        entry = midpoint if aggressive_entry else (event_high + tick if long else event_low - tick)
    stop = event_low - tick if long else event_high + tick
    risk = abs(entry - stop)
    sign = 1 if long else -1

    budget = None
    if max_loss_per_trade:
        budget = float(max_loss_per_trade)
    elif account_equity:
        budget = float(account_equity) * float(risk_pct)
    shares = int(budget // risk) if budget and risk > 0 else None
    if shares and pullback_scalp:
        # Pullback scalps start at 25% of normal size; adds still need reconfirmation.
        shares = int(shares * PULLBACK_SCALP_STARTER_FRACTION)
    if shares:
        lots = min(lots, shares)  # never plan more exit lots than shares
    lot_size = shares // lots if shares else None

    return {
        "side": side,
        "entry": _r(entry),
        "entry_type": "limit_at_event_midpoint" if aggressive_entry else ("buy_stop_above_event_high" if long else "sell_stop_below_event_low"),
        "event_stop": _r(stop),
        "risk_per_share": _r(risk),
        "stop_type": "event_stop",
        "max_loss_budget": _r(budget, 2),
        "shares": shares,
        "lots": lots,
        "lot_size": lot_size,
        "targets": {
            "lot_1": {"at": _r(entry + sign * risk), "r": 1.0, "rule": "First lot off at 1R or into the first elephant bar in your favor; stop to breakeven."},
            "lot_2": {"at": _r(entry + sign * 2 * risk), "r": 2.0, "rule": "Second lot at 2R or the next obstacle, whichever comes first."},
            "runner": {"at": None, "r": None, "rule": "Last lot trails bar-by-bar (one tick beyond the prior bar) until stopped or an exhausting elephant prints."},
        },
        "add_rule": "Add up to 50% of current size on the FIRST color change (RBI/GBI) pullback, only once the trade is in profit and initial risk is off. After the add, move the stop to halfway between the original entry and the add.",
        "invalidation": f"Trade is wrong if price trades {'below' if long else 'above'} {_r(stop)} — one tick beyond the event bar.",
        "mlpt_note": "If the event stop is too wide for your budget, size down (MLPT) rather than tighten the stop inside the bar.",
        "three_bar_rule": "If it is not working within 3 bars, get out or reduce.",
        "pullback_scalp_starter": PULLBACK_SCALP_STARTER_FRACTION if pullback_scalp else None,
        "eight_step_plan": {
            "market_context": "Read the 20/200, market state and Fab 4 box (velez_market_state).",
            "qualified_setup": "Checklist grade A or B (velez_checklist).",
            "trigger": "Break of the event bar.",
            "initial_stop": "One tick beyond the event bar.",
            "position_size": "Sized to the event stop (MLPT if too wide).",
            "trail_plan": "Breakeven at 1R, then bar-by-bar after two closes in favor.",
            "exit_and_review": "Lots at 1R / 2R / runner; journal the trade.",
            "add_on_plan": "First color change only, in P1/P2, max 50% of size.",
        },
    }


# ── Position management: bar-by-bar ──

def manage_position(
    side: str,
    entry: float,
    initial_stop: float,
    bars_since_entry: list[dict[str, Any]],
    current_stop: Optional[float] = None,
    tick: float = 0.01,
    lots_open: int = 3,
    context_bars: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    side = _norm_side(side)
    long = side == "long"
    if not bars_since_entry:
        raise ValueError("send the bars since entry (the entry bar first)")
    risk = abs(entry - initial_stop)
    if risk <= 0:
        raise ValueError("entry and initial_stop must differ")
    stop = initial_stop if current_stop is None else current_stop
    bars = bars_since_entry
    last = bars[-1]
    sign = 1 if long else -1
    r_now = sign * (last["c"] - entry) / risk
    best = max(sign * ((b["h"] if long else b["l"]) - entry) for b in bars) / risk
    reasons: list[str] = []
    actions: list[str] = []
    take_lots = 0

    if (last["l"] <= stop) if long else (last["h"] >= stop):
        return _mgmt("exit_stopped", stop, r_now, best, len(bars), 0,
                     [f"Price traded through the stop at {_r(stop)}. Out — no hoping."])

    # Breakeven once the trade has paid 1R.
    if best >= 1.0:
        new = max(stop, entry) if long else min(stop, entry)
        if new != stop:
            reasons.append("Trade reached 1R: stop to breakeven. Never let a winner turn into a loser.")
            stop = new

    # Bar-by-bar trail once two bars have closed beyond entry.
    closes_beyond = sum(1 for b in bars if sign * (b["c"] - entry) > 0)
    if closes_beyond >= 2 and len(bars) >= 2:
        prev = bars[-2]
        trail = prev["l"] - tick if long else prev["h"] + tick
        if (long and trail > stop) or (not long and trail < stop):
            reasons.append(f"Two bars closed in your favor: bar-by-bar trail to {_r(trail)} (one tick beyond the prior bar).")
            stop = trail
        actions.append("trail")

    # 3-bar rule.
    if len(bars) >= 3 and r_now <= 0 and best < 1.0:
        return _mgmt("exit_or_reduce", stop, r_now, best, len(bars), 0,
                     reasons + ["3-bar rule: three bars in and not working. Get out or cut size."])

    # Opposing events.
    history = (context_bars or []) + bars
    ev = classify_candle(last, history[:-1])
    opposing = set(ev["events"]) & ({"topping_tail", "bear_180", "bear_elephant"} if long else {"bottoming_tail", "bull_180", "bull_elephant"})
    if opposing:
        tight = last["l"] - tick if long else last["h"] + tick
        if (long and tight > stop) or (not long and tight < stop):
            stop = tight
        reasons.append(f"Opposing event {sorted(opposing)}: tighten to {_r(stop)}; exit on a break of this bar.")
        actions.append("tighten")

    # Sell into strength: exhausting elephant in your favor.
    favor = "bull_elephant" if long else "bear_elephant"
    if favor in ev["events"] and ev["detail"].get("elephant_origin") == "exhausting" and lots_open > 0:
        take_lots = max(take_lots, 1)
        reasons.append("Exhausting elephant in your favor (born far from the 20): sell into it — take a lot off.")
        actions.append("take_partial")

    # R targets.
    if best >= 2.0 and lots_open >= 2:
        take_lots = max(take_lots, 1)
        reasons.append("2R reached: second lot off; runner trails bar-by-bar.")
        actions.append("take_partial")
    elif best >= 1.0 and lots_open >= 3:
        take_lots = max(take_lots, 1)
        reasons.append("1R reached: first lot off.")
        actions.append("take_partial")

    if not reasons:
        reasons.append("Nothing to do: stop stays put, let the trade work.")
    precedence = ["take_partial", "tighten", "trail"]
    action = next((a for a in precedence if a in actions), "hold")
    return _mgmt(action, stop, r_now, best, len(bars), take_lots, reasons, actions)


def _mgmt(action, stop, r_now, best, held, take_lots, reasons, actions=None) -> dict[str, Any]:
    return {
        "action": action, "actions": sorted(set(actions or [action])), "stop": _r(stop), "current_r": round(r_now, 2),
        "max_favorable_r": round(best, 2), "bars_held": held,
        "take_lots": take_lots, "reasons": reasons,
    }


# ── The playbook ──

PRINCIPLES = [
    "Charts are the footprints of money. Trade what the bars say, not what you think.",
    "Two lines run the show: the 20 SMA (the trend's heartbeat) and the 200 SMA (the veto).",
    "The 200 does not create trades — it removes them. Don't buy under a falling 200, don't short over a rising one.",
    "Trade with the slope of the 20. Buy pullbacks to a rising 20; short rallies to a falling 20.",
    "Three states: narrow (the coil) — play the explosion; trending (the move) — play color changes at the 20; wide (the climax) — don't trade the trend, take profits or fade.",
    "Location first, pattern second. The same candle means different things at the 20, extended from the 20, or at the 200.",
    "Inside the Fab 4 trap zone nobody has control. Do less there.",
    "Enter on the break of the event bar; stop one tick beyond its other end (the event stop).",
    "Size to the stop, not the stop to the size. If the stop is too wide, trade smaller (MLPT).",
    "Trade in lots. Pay yourself into strength, trail the rest bar-by-bar.",
    "Never let a winner turn into a loser: 1R → stop to breakeven.",
    "If it isn't working in 3 bars, it probably isn't going to. Get out or reduce.",
    "Add to winners on the first color change, never to losers.",
    "Let the first 15 minutes settle (5 for gap plays), skip trend entries in the 11:30–1:30 midday chop, no new trades in the last 15 minutes, and trade with the market (SPY/QQQ).",
    "Trading is mostly psychological. The rules exist so you don't have to decide under pressure.",
]

PLAYBOOK: dict[str, dict[str, Any]] = {
    "elephant_bar": {
        "family": "continuation (igniting) / exit signal (exhausting)",
        "definition": "A wide-range bar whose body dwarfs recent bars (≈1.8×+ the last 5 bodies, top 30% of the last 20) with small wicks.",
        "location": "Igniting: originates AT or near the 20 SMA (or out of a narrow state / the Fab 4 box). Exhausting: originates far from the 20 after a run — do not buy it.",
        "entry": "Break of the elephant's high (long) / low (short), or a limit at its 50% body retracement when it's climactic or you'd be chasing.",
        "stop": "One tick beyond the opposite end of the elephant (event stop); 50% of the bar if it's very large and you entered at the midpoint.",
        "exit": "1R first lot, 2R second, runner bar-by-bar. An elephant that clears 3+ prior bars has the highest follow-through.",
        "avoid": ["Exhausting elephants", "No 20/200 location", "Chasing far from the trigger", "Middle of the trap zone"],
    },
    "bottoming_tail": {
        "family": "reversal (when extended) / continuation (at a rising 20)",
        "definition": "Lower wick ≥ 2/3 of the bar's range — sellers pushed and got rejected. An elephant bar that got reversed.",
        "location": "Extended below the 20 after a multi-bar decline, at a rising 200, or at a rising 20 on a pullback in an uptrend.",
        "entry": "Break of the tail bar's high, or a limit into the 50% of the tail.",
        "stop": "One tick below the tail's low.",
        "exit": "Target the 20 SMA first when reversing; 1R/2R lots otherwise. Don't assume a full trend reversal.",
        "avoid": ["Tail < 66% of range", "Mid-range location", "Below a falling 200 (unless at the 200 itself)"],
    },
    "topping_tail": {
        "family": "reversal (when extended) / continuation (at a falling 20)",
        "definition": "Upper wick ≥ 2/3 of the bar's range — buyers pushed and got rejected.",
        "location": "Extended above the 20 after a multi-bar rally, at a falling 200, or at a falling 20 on a bounce in a downtrend.",
        "entry": "Break of the tail bar's low, or a limit into the 50% of the tail.",
        "stop": "One tick above the tail's high.",
        "exit": "Target the 20 SMA first when reversing; 1R/2R lots otherwise.",
        "avoid": ["Tail < 66% of range", "Mid-range location", "Above a rising 200 (unless at the 200 itself)"],
    },
    "bull_180": {
        "family": "reversal",
        "definition": "A solid red bar followed by a solid green bar that recovers ≥80% of the red body. Sellers get run over inside one bar.",
        "location": "Most powerful far from the 20 (extended below it) or at the 200. At the 20 it's usually just noise.",
        "entry": "As soon as the second bar clears the first bar's high (no need to wait for the close), or break of bar two's high.",
        "stop": "One tick below the low of the two-bar sequence.",
        "exit": "First target the 20 SMA / 1R, then 2R or next structure.",
        "avoid": ["Recovery under 80%", "Small bodies", "Strong top-down opposition"],
    },
    "bear_180": {
        "family": "reversal",
        "definition": "A solid green bar followed by a solid red bar that erases ≥80% of the green body.",
        "location": "Most powerful far above the 20 or at the 200.",
        "entry": "When bar two breaks bar one's low, or break of bar two's low.",
        "stop": "One tick above the high of the two-bar sequence.",
        "exit": "First target the 20 SMA / 1R, then 2R or next structure.",
        "avoid": ["Recovery under 80%", "Small bodies"],
    },
    "velez_buy_setup": {
        "family": "continuation",
        "definition": "Uptrend (price > rising 20 > 200), 3–5 bar controlled pullback with lower highs toward the 20, then a bar that takes out the prior bar's high.",
        "location": "At or just above the rising 20 SMA (or at the 200 in a larger uptrend).",
        "entry": "Buy stop one tick above the high of the last pullback bar.",
        "stop": "One tick below the pullback low.",
        "exit": "Lots at 1R / 2R / prior high; runner bar-by-bar.",
        "avoid": ["Deep high-volume pullbacks", "Flat or falling 20", "Wide state extended above the 20"],
    },
    "velez_sell_setup": {
        "family": "continuation",
        "definition": "Downtrend (price < falling 20 < 200), 3–5 bar controlled bounce with higher lows toward the 20, then a bar that takes out the prior bar's low.",
        "location": "At or just below the falling 20 SMA.",
        "entry": "Sell stop one tick below the low of the last bounce bar.",
        "stop": "One tick above the bounce high.",
        "exit": "Lots at 1R / 2R / prior low; runner bar-by-bar.",
        "avoid": ["Violent bounces", "Flat or rising 20"],
    },
    "red_bar_ignored": {
        "family": "continuation / add",
        "definition": "Green control bar → small red 'rest' bar that holds inside the control bar → green signal bar that takes out the red bar's high.",
        "location": "In an uptrend above a rising 20.",
        "entry": "Break of the ignored red bar's high. First RBI after entry is THE add point.",
        "stop": "One tick below the ignored bar's low (or halfway between original entry and add).",
        "exit": "Managed with the original position plan.",
        "avoid": ["Red bar as big as the control bar", "Adding to a loser"],
    },
    "green_bar_ignored": {
        "family": "continuation / add",
        "definition": "Red control bar → small green rest bar → red signal bar that takes out the green bar's low.",
        "location": "In a downtrend below a falling 20.",
        "entry": "Break of the ignored green bar's low. First GBI after entry is THE add point.",
        "stop": "One tick above the ignored bar's high.",
        "exit": "Managed with the original position plan.",
        "avoid": ["Green bar as big as the control bar", "Adding to a loser"],
    },
    "nrb_acorn": {
        "family": "continuation",
        "definition": "A narrow-range pause bar (range ≤ ~65% of recent average) inside a trend — the acorn before the oak.",
        "location": "In a clean trend, ideally resting on the 20.",
        "entry": "Break of the NRB in the trend's direction.",
        "stop": "One tick beyond the opposite side of the NRB.",
        "exit": "1R/2R lots; runner bar-by-bar.",
        "avoid": ["NRBs in chop", "Obstacle right overhead"],
    },
    "three_bar_play": {
        "family": "continuation",
        "definition": "Igniting wide-range bar, then 1–2 tight rest bars holding in the top half of it, then a break.",
        "location": "Igniting bar starts at the 20 / out of a narrow state.",
        "entry": "Break of the rest bar's high (long) / low (short).",
        "stop": "One tick beyond the rest bar(s).",
        "exit": "1R/2R lots; runner bar-by-bar.",
        "avoid": ["Rest bars retracing >50% of the igniting bar", "Exhausting first bar"],
    },
    "fab4_trap_zone": {
        "family": "context filter",
        "definition": "Box drawn around the 20 SMA, 200 SMA, prior day's close and the last 45–60 minutes of price.",
        "location": "Above the box = green territory (long bias); below = red territory (short bias); inside = trap zone.",
        "entry": "Don't trade inside. Trade the first clean exit from the box with a qualified event bar.",
        "stop": "Beyond the event bar, or back inside the box.",
        "exit": "Standard lots.",
        "avoid": ["Fading the break back into the box", "Trading chop inside the box"],
    },
    "market_states": {
        "family": "context filter",
        "definition": "Three states read from the 20 and 200: NARROW (the coil), TRENDING (the move), WIDE (the climax). Pick the play by the state before picking the candle.",
        "location": "Narrow: 20 and 200 pinched/overlapping, flat and parallel. Trending: moderately separated, pulling apart evenly, 20 ramping ~45°. Wide: maximum gap, 20 steep, curving or exhausting.",
        "entry": "Narrow → play explosions out of it (elephant bars). Trending → play color changes at or near the 20. Wide → do not buy/short the trend.",
        "stop": "Per play.",
        "exit": "Wide state is where you take profits on trend trades, or fade/reverse.",
        "avoid": ["Trend entries in the wide state", "Fading a fresh explosion out of the narrow state", "Chasing far from the 20 in the trending state"],
    },
    "opening_gap": {
        "family": "open",
        "definition": "Gap vs prior close at 9:30. Go: first bar(s) hold the gap direction with clean space. Fade: gap into extension/200/prior structure and rejects.",
        "location": "Read the gap against the 20, 200, prior close and yesterday's range (Fab 4).",
        "entry": "Wait for the first 2-minute bar to close. Go: break of its high/low. Fade: rejection back toward the prior close.",
        "stop": "One tick beyond the first bar / the rejected extreme.",
        "exit": "Gap fill (prior close) is the principal fade target; 1R/2R lots for Go.",
        "avoid": ["Acting before the first bar closes", "Gaps with no space before an obstacle"],
    },
    "exits": {
        "family": "management",
        "definition": "Event stop 70% of the time, MLPT ~25%. 1R → breakeven. Two closes in favor → bar-by-bar trail. 3-bar rule. Sell into exhausting elephants.",
        "location": "n/a",
        "entry": "n/a",
        "stop": "Event stop = one tick beyond the event bar. MLPT = size down so the event stop fits your max loss.",
        "exit": "Lot 1 at 1R, lot 2 at 2R/obstacle, runner bar-by-bar. Opposing tail/180 against you → tighten to that bar.",
        "avoid": ["Moving a stop away from price", "Adding to losers", "Letting a 1R winner go red"],
    },
}


MARKET_STATES: dict[str, dict[str, str]] = {
    "narrow": {
        "name": "Narrow State (The Coil)",
        "sma_distance": "Extremely close together, pinched, or overlapping.",
        "sma_slant": "Flat, horizontal, and parallel.",
        "velez_action_rule": "Play explosions out of the narrow state (e.g., Elephant Bars).",
    },
    "trending": {
        "name": "Trending State (The Move)",
        "sma_distance": "Moderately separated, pulling apart evenly.",
        "sma_slant": "Ramping or declining at roughly a 45-degree angle.",
        "velez_action_rule": "Play color changes at or near the moving 20 SMA.",
    },
    "wide": {
        "name": "Wide State (The Climax)",
        "sma_distance": "Widely separated; maximum gap between lines.",
        "sma_slant": "Steeping heavily, curving, or showing exhaustion.",
        "velez_action_rule": "Do not buy/short trend. Prepare to take profits or fade/reverse.",
    },
    "transition": {
        "name": "Transition (between states)",
        "sma_distance": "Separated, but not pinched and not at a maximum.",
        "sma_slant": "Flat — no ramp.",
        "velez_action_rule": "No coil and no move: do less.",
    },
}


def playbook(query: str = "", setup: str = "") -> dict[str, Any]:
    key = setup.strip().lower().replace("-", "_").replace(" ", "_")
    needle = query.strip().lower()
    entries = {}
    for name, entry in PLAYBOOK.items():
        if key and key != name and key not in name:
            continue
        if needle and needle not in (name + " " + json.dumps(entry)).lower():
            continue
        entries[name] = entry
    return {
        "principles": PRINCIPLES if not key else [],
        "market_states": MARKET_STATES if not key or "state" in key else {},
        "setups": entries,
        "count": len(entries),
    }
