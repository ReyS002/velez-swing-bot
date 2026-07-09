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
from typing import Dict, List, Optional, Tuple

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
