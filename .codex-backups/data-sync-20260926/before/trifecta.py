"""
Trifecta — Multi-timeframe confluency gate.

Before executing any signal, confirms that higher timeframes agree with
the trade direction.  Uses Tradier (primary, paid, real-time) with
automatic yfinance fallback (free, 15-min delay).

Rules (auto-derived, config-overridable):
  Intraday:  2m→5m+15m, 5m→15m, 15m+→pass
  Swing:     60m→240m+D, 240m→D, D+→pass

Safety: any data-fetch failure lets the signal through — never block
a real trade on a transient API error.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd
import requests

logger = logging.getLogger("trifecta")

# ── Timeframe helpers ────────────────────────────────────────────────────

TF_MINUTES: Dict[str, int] = {
    "1": 1, "2": 2, "3": 3, "5": 5, "10": 10, "15": 15, "30": 30,
    "60": 60, "120": 120, "240": 240,
    "D": 1440, "W": 10080, "M": 43200,
}

YF_INTERVAL: Dict[str, str] = {
    "1": "1m", "2": "2m", "5": "5m", "15": "15m", "30": "30m",
    "60": "60m", "120": "2h", "240": "4h",
    "D": "1d", "W": "1wk", "M": "1mo",
}

TRADIER_INTERVAL: Dict[str, str] = {
    "60": "daily",  # no intraday — use daily as closest
    "120": "daily",
    "240": "daily",
    "D": "daily", "W": "weekly", "M": "monthly",
}

# Intervals that Tradier can actually serve (daily and above)
TRADIER_SUPPORTED = {"daily", "weekly", "monthly"}


def _tf_minutes(tf: str) -> int:
    """Convert timeframe string to minutes for comparison."""
    return TF_MINUTES.get(str(tf).strip(), 0)


def _yf_interval(tf: str) -> str:
    return YF_INTERVAL.get(str(tf).strip(), "1d")


def _tradier_interval(tf: str) -> str:
    return TRADIER_INTERVAL.get(str(tf).strip(), "daily")


# ── Default Trifecta chains ──────────────────────────────────────────────
# Signal TF → list of higher TFs that must confirm (in order, lowest first)

TRIFECTA_CHAINS: Dict[str, List[str]] = {
    # Intraday (2m/5m/15m/30m/60m)
    "1":  ["5", "15"],
    "2":  ["5", "15"],
    "3":  ["15"],
    "5":  ["15"],
    "10": ["60"],
    "15": [],               # top of intraday chain — pass through
    "30": ["240"],
    # Swing (60m/240m/D)
    "60":  ["240", "D"],
    "120": ["D"],
    "240": ["D"],
    "D":   [],              # top of swing chain — pass through
    "W":   [],
    "M":   [],
}


def get_trifecta_chain(signal_tf: str, config: dict) -> List[str]:
    """Return the list of higher timeframes that must confirm.

    Checks config override first (`trifecta.chains.signal_tf`), then
    falls back to built-in TRIFECTA_CHAINS.
    """
    tf = str(signal_tf).strip()
    override = config.get("trifecta", {}).get("chains", {}).get(tf)
    if override is not None:
        return [str(t) for t in override]
    return TRIFECTA_CHAINS.get(tf, [])


# ── Bar fetching ─────────────────────────────────────────────────────────

TRADIER_BASE = "https://api.tradier.com/v1"


def _tradier_token() -> Optional[str]:
    """Get Tradier token from environment, if available."""
    token = os.getenv("TRADIER_ACCESS_TOKEN", "").strip()
    return token if token else None


def fetch_bars_tradier(symbol: str, interval: str, days_back: int = 60,
                       token: Optional[str] = None) -> pd.DataFrame:
    """Fetch historical bars from Tradier (daily/weekly/monthly only).

    Returns DataFrame with columns: Open, High, Low, Close, Volume
    Returns empty DataFrame on failure or for unsupported intervals.
    """
    token = token or _tradier_token()
    if not token:
        return pd.DataFrame()

    tradier_int = _tradier_interval(interval)
    if tradier_int not in TRADIER_SUPPORTED:
        return pd.DataFrame()  # skip Tradier for intraday — use yfinance

    end = pd.Timestamp.today(tz="UTC")
    start = end - pd.Timedelta(days=days_back)

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    params = {
        "symbol": symbol,
        "interval": tradier_int,
        "start": start.strftime("%Y-%m-%d"),
        "end": end.strftime("%Y-%m-%d"),
    }

    for attempt in range(3):
        try:
            resp = requests.get(
                f"{TRADIER_BASE}/markets/history",
                headers=headers, params=params, timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                history = data.get("history")
                if history and history.get("day"):
                    rows = history["day"]
                    df = pd.DataFrame(rows)
                    df = df.rename(columns={
                        "date": "Date", "open": "Open", "high": "High",
                        "low": "Low", "close": "Close", "volume": "Volume",
                    })
                    df["Date"] = pd.to_datetime(df["Date"])
                    df = df.set_index("Date")
                    df = df[["Open", "High", "Low", "Close", "Volume"]]
                    df = df.astype(float)
                    return df
                return pd.DataFrame()
            elif resp.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            else:
                logger.debug("tradier_http_%d", resp.status_code)
                return pd.DataFrame()
        except Exception as exc:
            logger.debug("tradier_fetch_error: %s", exc)
            time.sleep(1)
    return pd.DataFrame()


def fetch_bars_yfinance(symbol: str, interval: str, days_back: int = 60) -> pd.DataFrame:
    """Fetch historical bars from yfinance (fallback).

    Returns DataFrame with columns: Open, High, Low, Close, Volume
    Returns empty DataFrame on failure.
    """
    try:
        import yfinance as yf
    except ImportError:
        return pd.DataFrame()

    try:
        yf_int = _yf_interval(interval)

        # Direct lookup keyed on the bot's OWN interval — do not scan.
        #
        # Previous implementation iterated the full period_map and only
        # `break`-ed once _tf_minutes(tf) < _tf_minutes(interval). For any
        # short interval (e.g. a 1-min scanner tick) that condition is
        # never true against the map's smallest keys, so the loop walked
        # every entry and always landed on the LAST one ("D" -> "1y").
        # Requesting 1-minute granularity over a 1-year period is rejected
        # by Yahoo Finance (max 8 days of 1m data per request), so every
        # fetch silently failed and returned an empty DataFrame — which is
        # exactly what kept the Arena bots' scanners stuck in "warming"
        # mode with warmed_symbols=0 indefinitely.
        period_map = {1: "5d", 2: "5d", 5: "5d", 10: "1mo",
                      15: "1mo", 30: "1mo", 60: "3mo",
                      120: "6mo", 240: "6mo", "D": "1y"}
        raw = str(interval).strip()
        lookup_key = int(raw) if raw.isdigit() else raw
        period = period_map.get(lookup_key, "3mo")  # safe default for unmapped codes

        df = yf.download(symbol, period=period, interval=yf_int, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        if df.empty:
            return pd.DataFrame()
        return df[["Open", "High", "Low", "Close", "Volume"]]
    except Exception as exc:
        logger.debug("yfinance_fetch_error: %s", exc)
        return pd.DataFrame()


def fetch_bars(symbol: str, interval: str, days_back: int = 60,
               token: Optional[str] = None) -> pd.DataFrame:
    """Fetch bars — Tradier primary, yfinance fallback.

    Returns DataFrame with OHLCV columns, or empty on total failure.
    """
    df = fetch_bars_tradier(symbol, interval, days_back, token)
    if not df.empty:
        logger.debug("trifecta_bars_tradier: %s %s → %d bars", symbol, interval, len(df))
        return df

    df = fetch_bars_yfinance(symbol, interval, days_back)
    if not df.empty:
        logger.debug("trifecta_bars_yfinance: %s %s → %d bars", symbol, interval, len(df))
    return df


# ── Trend check on a single timeframe ────────────────────────────────────

def _sma(series: pd.Series, period: int) -> pd.Series:
    """Simple moving average."""
    return series.rolling(window=period, min_periods=1).mean()


def check_timeframe_trend(df: pd.DataFrame, side: str,
                          min_sma200_bars: int = 50) -> Tuple[bool, str]:
    """Check if a single timeframe's trend supports the trade direction.

    Args:
        df: OHLCV DataFrame (must have 'Close' column)
        side: 'buy' or 'sell'
        min_sma200_bars: minimum bars for SMA200 to be meaningful

    Returns:
        (passed: bool, detail: str)
          passed=True  → trend agrees
          passed=False → trend opposes (detail explains why)
    """
    if df.empty or len(df) < 3:
        return False, f"insufficient_bars:{len(df)}"

    close = df["Close"].astype(float)
    sma20 = _sma(close, 20)
    sma200 = _sma(close, 200)

    last_sma20 = float(sma20.iloc[-1])
    last_sma200 = float(sma200.iloc[-1])

    if len(df) < min_sma200_bars:
        # Not enough data for reliable SMA200 — fall back to SMA20 slope only
        sma20_slope = sma20.iloc[-1] - sma20.iloc[-min(len(df), 5)]
        if side == "buy" and sma20_slope < 0:
            return False, f"sma20_declining:slope={sma20_slope:.4f}"
        if side == "sell" and sma20_slope > 0:
            return False, f"sma20_rising:slope={sma20_slope:.4f}"
        return True, "ok_sma20_only"

    import numpy as np
    if np.isnan(last_sma20) or np.isnan(last_sma200):
        return False, "sma_nan"

    # Primary check: SMA20 vs SMA200
    trend_up = last_sma20 > last_sma200

    if side == "buy" and not trend_up:
        return False, (f"sma20_below_sma200:"
                       f"SMA20={last_sma20:.2f}_SMA200={last_sma200:.2f}")
    if side == "sell" and trend_up:
        return False, (f"sma20_above_sma200:"
                       f"SMA20={last_sma20:.2f}_SMA200={last_sma200:.2f}")

    # Secondary check: SMA20 slope (3 most recent bars)
    sma20_slope = sma20.iloc[-1] - sma20.iloc[-min(len(df), 4)]
    if side == "buy" and sma20_slope < 0:
        return False, f"sma20_declining:slope={sma20_slope:.4f}"
    if side == "sell" and sma20_slope > 0:
        return False, f"sma20_rising:slope={sma20_slope:.4f}"

    return True, "ok"


# ── Main Trifecta check ──────────────────────────────────────────────────

def check_trifecta(symbol: str, signal_tf: str, side: str,
                   config: dict, log: Optional[logging.Logger] = None,
                   tradier_token: Optional[str] = None) -> Optional[str]:
    """Run the full Trifecta confluency check.

    Args:
        symbol: ticker (e.g. 'NVDA')
        signal_tf: signal's timeframe (e.g. '2', '60', 'D')
        side: 'buy' or 'sell'
        config: bot config dict (velez_strategy section)
        log: optional logger (uses module logger if None)
        tradier_token: Tradier API token (reads from env if None)

    Returns:
        None → passed (all higher TFs agree)
        str   → reason for rejection (ready to pass to WebhookDecision)
    """
    log = log or logger
    cfg = config.get("trifecta", {})
    if not cfg.get("enabled", True):
        return None

    chain = get_trifecta_chain(signal_tf, cfg)
    if not chain:
        log.debug("trifecta_pass_through", extra={
            "symbol": symbol, "tf": signal_tf, "side": side,
            "reason": "top_of_chain",
        })
        return None

    token = tradier_token or _tradier_token()

    for htf in chain:
        htf_label = f"{htf}m" if htf.isdigit() else htf
        try:
            df = fetch_bars(symbol, htf, token=token)
            if df.empty:
                log.warning("trifecta_skip_no_data", extra={
                    "symbol": symbol, "signal_tf": signal_tf,
                    "check_tf": htf, "side": side,
                    "reason": "no_bars_available",
                })
                continue  # let signal through — don't block on missing data

            passed, detail = check_timeframe_trend(df, side)
            if not passed:
                log.info("trifecta_rejected", extra={
                    "symbol": symbol, "signal_tf": signal_tf,
                    "check_tf": htf, "side": side,
                    "detail": detail,
                })
                return (f"trifecta_rejected:{symbol} {signal_tf}m "
                        f"requires {htf_label} confirmation — {detail}")

            log.debug("trifecta_ok", extra={
                "symbol": symbol, "signal_tf": signal_tf,
                "check_tf": htf, "side": side, "detail": detail,
            })
        except Exception as exc:
            log.warning("trifecta_error", extra={
                "symbol": symbol, "signal_tf": signal_tf,
                "check_tf": htf, "side": side, "error": str(exc),
            })
            # Let signal through on errors — safety first
            continue

    return None  # All higher TFs confirmed


def score_trifecta(symbol: str, signal_tf: str, side: str,
                   config: dict, log=None,
                   tradier_token: Optional[str] = None) -> float:
    """Score multi-timeframe alignment 0.0-1.0.

    Unlike check_trifecta (binary pass/fail), this returns a numeric
    grade. 1.0 = all higher TFs perfectly aligned. 0.0 = all opposed.
    Used by the stacking/lot-sizing extension to refine position size.

    Scoring:
      - Each higher TF gets 1 point if trend aligns, 0 if not
      - Bonuses for strong SMA slope and wide SMA gap
      - Normalized to 0-1
    """
    log = log or logger
    cfg = config.get("trifecta", {})
    if not cfg.get("enabled", True):
        return 1.0  # disabled = no penalty

    chain = get_trifecta_chain(signal_tf, cfg)
    if not chain:
        return 1.0  # top of chain = full score

    token = tradier_token or _tradier_token()
    total_score = 0.0
    max_possible = float(len(chain))

    for htf in chain:
        try:
            df = fetch_bars(symbol, htf, token=token)
            if df.empty or len(df) < 50:
                max_possible -= 1  # can't judge this TF
                continue

            sma20 = df["Close"].rolling(20).mean()
            sma200 = df["Close"].rolling(200).mean()
            last_sma20_val = sma20.iloc[-1]
            last_sma200_val = sma200.iloc[-1]

            if pd.isna(last_sma20_val) or pd.isna(last_sma200_val):
                max_possible -= 1
                continue

            is_bull = side.lower() == "buy"

            # Core trend alignment
            trend_aligned = (is_bull and last_sma20_val > last_sma200_val) or \
                            (not is_bull and last_sma20_val < last_sma200_val)

            if not trend_aligned:
                continue  # 0 for this TF

            tf_score = 1.0

            # Bonus: SMA gap width (wider = stronger trend)
            sma_gap_pct = abs(last_sma20_val - last_sma200_val) / max(last_sma200_val, 1e-9)
            gap_bonus = min(sma_gap_pct / 0.02, 0.25)  # up to +0.25 for 2%+ gap
            tf_score += gap_bonus

            # Bonus: SMA slope steepness
            if len(sma20) >= 5:
                slope = sma20.iloc[-1] - sma20.iloc[-5]
                steep = abs(slope) / max(last_sma20_val * 0.1, 1e-9)
                slope_bonus = min(steep, 0.25)
                tf_score += slope_bonus

            total_score += min(tf_score, 1.5)  # cap per-TF at 1.5

        except Exception:
            max_possible -= 1
            continue

    if max_possible <= 0:
        return 1.0  # no TFs to judge = pass

    return round(min(total_score / max_possible, 1.0), 2)


# ── Webhook intake confluence ────────────────────────────────────────────

def normalize_timeframe(timeframe: str) -> str:
    """Normalize common TradingView timeframe labels to the internal codes."""
    value = str(timeframe or "").strip().lower().replace(" ", "")
    aliases = {
        "1m": "1", "1min": "1", "1minute": "1",
        "2m": "2", "2min": "2", "2minute": "2",
        "3m": "3", "3min": "3", "3minute": "3",
        "5m": "5", "5min": "5", "5minute": "5",
        "10m": "10", "10min": "10", "10minute": "10",
        "15m": "15", "15min": "15", "15minute": "15",
        "30m": "30", "30min": "30", "30minute": "30",
        "1h": "60", "60m": "60", "60min": "60", "60minute": "60",
        "2h": "120", "120m": "120", "120min": "120",
        "4h": "240", "240m": "240", "240min": "240",
        "1d": "D", "day": "D", "daily": "D",
    }
    return aliases.get(value, str(timeframe or "").strip())


def _freshness_receipt(frame: pd.DataFrame, timeframe: str, cfg: dict) -> dict:
    """Return an auditable freshness check without guessing when timestamps are absent."""
    limits = cfg.get("max_bar_age_minutes", {}) if isinstance(cfg, dict) else {}
    try:
        max_age_minutes = float(limits.get(str(timeframe), limits.get("default", 0)) or 0)
    except (TypeError, ValueError):
        max_age_minutes = 0.0
    result = {"checked": max_age_minutes > 0, "max_age_minutes": max_age_minutes, "age_minutes": None, "fresh": True}
    if max_age_minutes <= 0 or frame.empty:
        return result
    if not isinstance(frame.index, pd.DatetimeIndex):
        result.update({"checked": False, "reason": "timestamp_unavailable"})
        return result
    try:
        timestamp = pd.Timestamp(frame.index[-1])
    except Exception:
        result.update({"checked": False, "reason": "timestamp_unavailable"})
        return result
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    age_minutes = max(0.0, (datetime.now(timezone.utc) - timestamp.to_pydatetime()).total_seconds() / 60.0)
    result.update({"age_minutes": round(age_minutes, 2), "fresh": age_minutes <= max_age_minutes})
    return result


def score_webhook_confluence(
    symbol: str,
    signal_tf: str,
    side: str,
    config: dict,
    *,
    log: Optional[logging.Logger] = None,
    fetcher: Optional[Callable[[str, str], pd.DataFrame]] = None,
) -> dict:
    """Score the signal, 1H, and 4H trends before a webhook can size risk.

    A single opposing higher timeframe turns an otherwise valid setup into a
    quarter-sized starter.  When both higher timeframes oppose, it is skipped.
    A data outage must never become an unrecorded full-size entry.  A missing
    signal timeframe rejects the webhook; a missing higher timeframe uses the
    configured reduced-size fallback (or skips when explicitly configured).
    """
    log = log or logger
    cfg = config.get("webhook_confluence", {}) if isinstance(config, dict) else {}
    if not cfg.get("enabled", False):
        return {
            "enabled": False,
            "signal_timeframe": normalize_timeframe(signal_tf),
            "timeframes": {},
            "higher_opposed": 0,
            "multiplier": 1.0,
            "action": "full_size",
            "reason": "disabled",
        }

    normalized_signal_tf = normalize_timeframe(signal_tf or cfg.get("default_signal_timeframe", "15"))
    higher_timeframes = [normalize_timeframe(item) for item in cfg.get("higher_timeframes", ["60", "240"])]
    required = []
    for timeframe in [normalized_signal_tf, *higher_timeframes]:
        if timeframe and timeframe not in required:
            required.append(timeframe)
    fetch = fetcher or (lambda wanted_symbol, wanted_tf: fetch_bars(wanted_symbol, wanted_tf))
    timeframes: Dict[str, dict] = {}
    for timeframe in required:
        try:
            frame = fetch(symbol, timeframe)
            if frame is None or frame.empty:
                timeframes[timeframe] = {"state": "unavailable", "detail": "no_bars_available"}
                continue
            aligned, detail = check_timeframe_trend(frame, side)
            freshness = _freshness_receipt(frame, timeframe, cfg)
            timeframes[timeframe] = {
                "state": "stale" if not freshness["fresh"] else "aligned" if aligned else "opposed",
                "detail": detail,
                "bars": len(frame),
                "freshness": freshness,
            }
        except Exception as exc:  # Fail open only for unavailable data, never for known opposition.
            timeframes[timeframe] = {"state": "unavailable", "detail": f"fetch_error:{str(exc)[:120]}"}

    # A 1H signal has only 4H above it, while a 4H signal has no higher
    # requested timeframe.  The signal timeframe is recorded for audit but is
    # not treated as a higher-timeframe conflict.
    higher_to_score = [timeframe for timeframe in higher_timeframes if timeframe != normalized_signal_tf]
    opposed = [timeframe for timeframe in higher_to_score if timeframes.get(timeframe, {}).get("state") == "opposed"]
    signal_state = timeframes.get(normalized_signal_tf, {}).get("state")
    unavailable_higher = [
        timeframe for timeframe in higher_to_score
        if timeframes.get(timeframe, {}).get("state") in {"unavailable", "stale"}
    ]
    if signal_state in {"unavailable", "stale"}:
        multiplier, action, reason = 0.0, "skip", "signal_timeframe_data_unavailable"
    elif signal_state == "opposed" and cfg.get("skip_signal_trend_conflict", True):
        multiplier, action, reason = 0.0, "skip", "signal_timeframe_trend_opposed"
    elif len(opposed) >= 2:
        multiplier, action, reason = 0.0, "skip", "both_higher_timeframes_opposed"
    elif unavailable_higher:
        unavailable_action = str(cfg.get("unavailable_higher_timeframe_action", "starter")).lower()
        if unavailable_action == "skip":
            multiplier, action, reason = 0.0, "skip", "higher_timeframe_data_unavailable"
        else:
            multiplier = float(cfg.get("unavailable_starter_multiplier", cfg.get("conflict_starter_multiplier", 0.25)))
            action, reason = "starter", "higher_timeframe_data_unavailable:" + ",".join(unavailable_higher)
    elif len(opposed) == 1:
        multiplier, action, reason = float(cfg.get("conflict_starter_multiplier", 0.25)), "starter", f"higher_timeframe_opposed:{opposed[0]}"
    else:
        multiplier, action, reason = 1.0, "full_size", "all_available_higher_timeframes_aligned"

    result = {
        "enabled": True,
        "signal_timeframe": normalized_signal_tf,
        "higher_timeframes": higher_to_score,
        "timeframes": timeframes,
        "higher_opposed": len(opposed),
        "multiplier": max(0.0, min(multiplier, 1.0)),
        "action": action,
        "reason": reason,
    }
    log.info("webhook_confluence_scored", extra={"symbol": symbol, "side": side, **result})
    return result
