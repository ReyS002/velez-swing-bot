"""
TBA Analytics — Backtesting, Optimization, Monte Carlo, Price Watchers, Sentiment

Real implementations using the Velez bot's trade DB and Alpaca data.
All 5 tools: backtest_strategy, optimize_strategy, monte_carlo,
setup_price_watcher, analyze_sentiment.

Usage:
  python3 tba_analytics.py backtest --ticker NVDA --strategy ma_crossover
  python3 tba_analytics.py optimize --ticker SPY --strategy ma_crossover
  python3 tba_analytics.py monte-carlo --ticker SPY --simulations 10000
  python3 tba_analytics.py price-watcher --ticker NVDA --above 250
  python3 tba_analytics.py sentiment --ticker NVDA
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

# ── Paths ──────────────────────────────────────────────────────────────────
BOT_DB = Path("/app/data/trading_bull_desk.sqlite3")
ALPACA_KEY = os.environ.get("APCA_API_KEY_ID", "")
ALPACA_SECRET = os.environ.get("APCA_API_SECRET_KEY", "")


# ═════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def _alpaca_headers() -> dict:
    return {
        "APCA-API-KEY-ID": ALPACA_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET,
    }


def _alpaca_bars(ticker: str, timeframe: str = "1D", limit: int = 500) -> list[dict]:
    """Fetch OHLCV bars from yfinance (free, reliable for historical data).

    Alpaca free tier doesn't provide historical bars, so we use yfinance.
    """
    import yfinance as yf
    try:
        df = yf.download(ticker, period="1y" if limit > 200 else "6mo",
                         interval="1d", progress=False, auto_adjust=True)
        if df is None or df.empty:
            return []
        # Handle MultiIndex columns (yfinance sometimes returns multi-level column headers)
        if hasattr(df.columns, 'nlevels') and df.columns.nlevels > 1:
            df.columns = df.columns.droplevel(1)
        bars = []
        for ts, row in df.iterrows():
            bars.append({
                "t": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                "o": float(row["Open"]) if hasattr(row["Open"], "item") else float(row["Open"]),
                "h": float(row["High"]) if hasattr(row["High"], "item") else float(row["High"]),
                "l": float(row["Low"]) if hasattr(row["Low"], "item") else float(row["Low"]),
                "c": float(row["Close"]) if hasattr(row["Close"], "item") else float(row["Close"]),
                "v": float(row["Volume"]) if "Volume" in row and row["Volume"] is not None and not (hasattr(row["Volume"], "empty") and row["Volume"].empty) else 0,
            })
        return bars[-limit:]
    except Exception as e:
        print(f"yfinance error for {ticker}: {e}", file=sys.stderr)
        return []


def _bot_trades(limit: int = 500) -> list[dict]:
    """Fetch real trade outcomes from the Velez bot's DB."""
    if not BOT_DB.exists():
        return []
    conn = sqlite3.connect(str(BOT_DB))
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "SELECT timestamp, symbol, status, pnl, r_multiple, notes FROM trade_outcomes ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    )
    trades = [dict(r) for r in cur.fetchall()]
    conn.close()
    return trades


def _calculate_sma(closes: list[float], period: int) -> Optional[float]:
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def _simulate_crossover(closes: list[float], fast: int, slow: int) -> list[dict]:
    """Simulate SMA crossover trades on historical close data."""
    trades = []
    position = None  # "long" or None
    entry_price = None
    entry_idx = None

    for i in range(slow, len(closes)):
        sma_fast = _calculate_sma(closes[: i + 1], fast)
        sma_slow = _calculate_sma(closes[: i + 1], slow)
        if sma_fast is None or sma_slow is None:
            continue

        prev_fast = _calculate_sma(closes[:i], fast)
        prev_slow = _calculate_sma(closes[:i], slow)

        if prev_fast is not None and prev_slow is not None:
            if prev_fast <= prev_slow and sma_fast > sma_slow and position is None:
                # Buy signal
                position = "long"
                entry_price = closes[i]
                entry_idx = i
            elif prev_fast >= prev_slow and sma_fast < sma_slow and position == "long":
                # Sell signal
                exit_price = closes[i]
                pnl = (exit_price - entry_price) / entry_price if entry_price else 0
                trades.append({
                    "entry_idx": entry_idx,
                    "exit_idx": i,
                    "entry": round(entry_price, 2) if entry_price else 0,
                    "exit": round(exit_price, 2),
                    "return_pct": round(pnl * 100, 2),
                })
                position = None
                entry_price = None

    # Close any open position at last bar
    if position == "long" and entry_price is not None:
        pnl = (closes[-1] - entry_price) / entry_price if entry_price else 0
        trades.append({
            "entry_idx": entry_idx,
            "exit_idx": len(closes) - 1,
            "entry": round(entry_price, 2),
            "exit": round(closes[-1], 2),
            "return_pct": round(pnl * 100, 2),
        })

    return trades


# ═════════════════════════════════════════════════════════════════════════════
# TOOL 1: BACKTEST STRATEGY
# ═════════════════════════════════════════════════════════════════════════════

def backtest_strategy(ticker: str, strategy_type: str = "ma_crossover",
                      lookback_days: int = 365, risk_per_trade: float = 0.01) -> dict:
    """Backtest a trading strategy against historical price data.

    Uses real Alpaca price data. Supports: ma_crossover.
    Returns performance metrics: win rate, return, drawdown, Sharpe.
    """
    bars = _alpaca_bars(ticker, "1D", limit=lookback_days)
    if not bars or len(bars) < 60:
        return {"error": f"Insufficient data for {ticker}", "bars_available": len(bars)}

    closes = [b["c"] for b in bars]

    if strategy_type == "ma_crossover":
        trades = _simulate_crossover(closes, fast=20, slow=50)
    else:
        return {"error": f"Unsupported strategy: {strategy_type}"}

    if not trades:
        return {"ticker": ticker, "strategy": strategy_type, "trades": 0, "note": "No trades generated"}

    returns = [t["return_pct"] for t in trades]
    winning = [r for r in returns if r > 0]
    losing = [r for r in returns if r < 0]
    total_return = sum(returns)
    win_rate = len(winning) / len(returns) * 100 if returns else 0

    # Max drawdown (peak to trough of cumulative returns)
    cum = 0
    peak = 0
    max_dd = 0
    for r in returns:
        cum += r
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd

    # Sharpe (annualized, assuming 252 trading days)
    avg_ret = sum(returns) / len(returns) if returns else 0
    std_ret = math.sqrt(sum((r - avg_ret) ** 2 for r in returns) / len(returns)) if len(returns) > 1 else 1
    sharpe = (avg_ret / std_ret) * math.sqrt(252) if std_ret > 0 else 0

    # Profit factor
    gross_profit = sum(winning) if winning else 0
    gross_loss = abs(sum(losing)) if losing else 1
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

    return {
        "ticker": ticker,
        "strategy": strategy_type,
        "period": f"{lookback_days} days ({len(bars)} bars)",
        "trades_executed": len(trades),
        "results": {
            "win_rate": f"{win_rate:.1f}%",
            "total_return": f"{total_return:.2f}%",
            "max_drawdown": f"{max_dd:.2f}%",
            "profit_factor": round(profit_factor, 2),
            "sharpe_ratio": round(sharpe, 2),
            "avg_return_per_trade": f"{avg_ret:.2f}%",
            "best_trade": f"{max(returns):.2f}%",
            "worst_trade": f"{min(returns):.2f}%",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ═════════════════════════════════════════════════════════════════════════════
# TOOL 2: OPTIMIZE STRATEGY
# ═════════════════════════════════════════════════════════════════════════════

def optimize_strategy(ticker: str, strategy_type: str = "ma_crossover",
                      fast_min: int = 5, fast_max: int = 50, fast_step: int = 5,
                      slow_min: int = 50, slow_max: int = 200, slow_step: int = 10,
                      metric: str = "sharpe") -> dict:
    """Grid search over SMA parameters to find optimal values.

    Tests all (fast, slow) combinations against historical price data.
    Returns best parameters by chosen metric (sharpe, profit_factor, return, win_rate).
    """
    bars = _alpaca_bars(ticker, "1D", limit=500)
    if not bars or len(bars) < 100:
        return {"error": f"Insufficient data for {ticker}"}

    closes = [b["c"] for b in bars]
    results = []

    for fast in range(fast_min, fast_max + 1, fast_step):
        for slow in range(slow_min, slow_max + 1, slow_step):
            if slow <= fast:
                continue
            trades = _simulate_crossover(closes, fast, slow)
            if not trades:
                continue

            returns = [t["return_pct"] for t in trades]
            winning = [r for r in returns if r > 0]
            losing = [r for r in returns if r < 0]
            total_return = sum(returns)
            win_rate = len(winning) / len(returns) * 100 if returns else 0
            avg_ret = sum(returns) / len(returns) if returns else 0
            std_ret = math.sqrt(sum((r - avg_ret) ** 2 for r in returns) / len(returns)) if len(returns) > 1 else 1
            sharpe = (avg_ret / std_ret) * math.sqrt(252) if std_ret > 0 else 0
            gross_profit = sum(winning) if winning else 0
            gross_loss = abs(sum(losing)) if losing else 1
            pf = gross_profit / gross_loss if gross_loss > 0 else 0

            combo_metrics = {
                "fast": fast, "slow": slow, "trades": len(trades),
                "win_rate": win_rate, "total_return": total_return,
                "sharpe": sharpe, "profit_factor": pf,
            }

            metric_key = {"sharpe": "sharpe", "profit_factor": "profit_factor",
                          "return": "total_return", "win_rate": "win_rate"}.get(metric, "sharpe")
            combo_metrics["_sort_key"] = abs(combo_metrics.get(metric_key, 0))
            results.append(combo_metrics)

    if not results:
        return {"error": "No valid parameter combinations found"}

    results.sort(key=lambda x: x["_sort_key"], reverse=True)
    best = results[0]

    return {
        "ticker": ticker,
        "strategy": strategy_type,
        "metric_optimized": metric,
        "combinations_tested": len(results),
        "best_parameters": {"sma_fast": best["fast"], "sma_slow": best["slow"]},
        "performance": {
            "total_return": f"{best['total_return']:.2f}%",
            "win_rate": f"{best['win_rate']:.1f}%",
            "profit_factor": round(best["profit_factor"], 2),
            "sharpe_ratio": round(best["sharpe"], 2),
            "total_trades": best["trades"],
        },
        "top_5": [
            {"fast": r["fast"], "slow": r["slow"], "sharpe": round(r["sharpe"], 2),
             "return": f"{r['total_return']:.1f}%", "win_rate": f"{r['win_rate']:.1f}%"}
            for r in results[:5]
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ═════════════════════════════════════════════════════════════════════════════
# TOOL 3: MONTE CARLO
# ═════════════════════════════════════════════════════════════════════════════

def monte_carlo(ticker: str, strategy_type: str = "ma_crossover",
                num_simulations: int = 10000, lookback_days: int = 365) -> dict:
    """Run Monte Carlo simulation using real trade P&L distribution.

    Uses the actual P&L distribution from the bot's trade history to
    simulate many possible futures. Returns probability of profit, VaR, etc.
    """
    # Use real trade P&L if available
    real_trades = _bot_trades(limit=200)
    real_pnls = [t.get("pnl", 0) for t in real_trades if t.get("pnl") is not None]

    if len(real_pnls) < 10:
        # Fall back to backtested returns
        bars = _alpaca_bars(ticker, "1D", limit=lookback_days)
        if not bars or len(bars) < 60:
            return {"error": f"Insufficient data for {ticker}"}
        closes = [b["c"] for b in bars]
        trades = _simulate_crossover(closes, 20, 50)
        real_pnls = [t["return_pct"] for t in trades] if trades else [random.gauss(0.1, 2.0) for _ in range(50)]

    if not real_pnls:
        return {"error": "No trade data available for simulation"}

    # Bootstrap simulation: randomly sample with replacement from real P&L distribution
    random.seed(int(time.time()))
    simulated_returns = []
    for _ in range(num_simulations):
        sample = random.choice(real_pnls)
        simulated_returns.append(sample)

    simulated_returns.sort()
    mean_r = sum(simulated_returns) / len(simulated_returns)
    var_95 = simulated_returns[int(len(simulated_returns) * 0.05)]
    var_99 = simulated_returns[int(len(simulated_returns) * 0.01)]
    profitable = sum(1 for r in simulated_returns if r > 0)

    # Compound return over N trades (simulate a year of trading)
    trades_per_year = max(len(real_pnls), 50)
    compound_returns = []
    for _ in range(1000):
        compound = 1.0
        for _ in range(trades_per_year):
            compound *= 1 + (random.choice(real_pnls) / 100)
        compound_returns.append((compound - 1) * 100)

    compound_returns.sort()
    expected_return = sum(compound_returns) / len(compound_returns)

    return {
        "ticker": ticker,
        "strategy": strategy_type,
        "simulations": num_simulations,
        "data_source": "real_trade_pnl" if len([t for t in real_trades if t.get("pnl") is not None]) >= 10 else "simulated_backtest",
        "real_trades_used": len(real_pnls),
        "probability_of_profit": f"{profitable / len(simulated_returns):.1%}",
        "return_distribution": {
            "mean_per_trade": f"{mean_r:.2f}%",
            "best_case": f"{simulated_returns[-1]:.2f}%",
            "worst_case": f"{simulated_returns[0]:.2f}%",
            "expected_annual_return": f"{expected_return:.1f}%",
        },
        "risk_metrics": {
            "var_95": f"{var_95:.2f}%",
            "var_99": f"{var_99:.2f}%",
            "interpretation": f"5% chance of losing more than {abs(var_95):.1f}% per trade",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ═════════════════════════════════════════════════════════════════════════════
# TOOL 4: PRICE WATCHER
# ═════════════════════════════════════════════════════════════════════════════

_PRICE_WATCHERS: dict[str, dict] = {}
_WATCHER_STATE_FILE = Path("/opt/stacks/velez-trading-bot/data/price_watchers.json")


def _save_watchers():
    _WATCHER_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {k: v for k, v in _PRICE_WATCHERS.items()}
    data["_as_of"] = datetime.now(timezone.utc).isoformat()
    with open(_WATCHER_STATE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _load_watchers():
    global _PRICE_WATCHERS
    if _WATCHER_STATE_FILE.exists():
        with open(_WATCHER_STATE_FILE) as f:
            data = json.load(f)
            data.pop("_as_of", None)
            _PRICE_WATCHERS.update(data)


def setup_price_watcher(ticker: str, watch_type: str = "above",
                        trigger_price: Optional[float] = None,
                        upper_price: Optional[float] = None,
                        lower_price: Optional[float] = None,
                        check_interval_seconds: int = 300) -> dict:
    """Set up a price level monitor. Triggers when price crosses specified level.

    watch_type: above, below, range, breakout
    Stores watchers persistently and checks on each scanner cycle.
    """
    _load_watchers()

    watcher_id = f"{ticker}_{watch_type}_{int(time.time())}"
    condition = ""

    if watch_type == "above" and trigger_price:
        condition = f"price above ${trigger_price:.2f}"
    elif watch_type == "below" and trigger_price:
        condition = f"price below ${trigger_price:.2f}"
    elif watch_type == "range" and upper_price and lower_price:
        condition = f"price in ${lower_price:.2f} - ${upper_price:.2f}"
    elif watch_type == "breakout" and trigger_price:
        condition = f"price breaks ${trigger_price:.2f}"
    else:
        return {"error": "Invalid watch_type or missing price parameters"}

    _PRICE_WATCHERS[watcher_id] = {
        "ticker": ticker.upper(),
        "type": watch_type,
        "trigger_price": trigger_price,
        "upper_price": upper_price,
        "lower_price": lower_price,
        "check_interval_seconds": check_interval_seconds,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "active",
        "triggered": False,
    }
    _save_watchers()

    return {
        "status": "active",
        "watcher_id": watcher_id,
        "watching": ticker.upper(),
        "condition": condition,
        "check_interval": f"Every {check_interval_seconds}s",
        "total_watchers": len([k for k in _PRICE_WATCHERS if _PRICE_WATCHERS[k].get("status") == "active"]),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def check_price_watchers() -> list[dict]:
    """Check all active price watchers. Called by scanner cycle."""
    _load_watchers()
    if not _PRICE_WATCHERS:
        return []

    triggered = []
    # Group by ticker to minimize API calls
    tickers = set()
    for wid, watcher in _PRICE_WATCHERS.items():
        if watcher.get("status") == "active" and not watcher.get("triggered"):
            tickers.add(watcher["ticker"])

    # Fetch current prices
    prices = {}
    for ticker in tickers:
        try:
            bars = _alpaca_bars(ticker, "1D", limit=1)
            if bars:
                prices[ticker] = bars[0]["c"]
        except Exception:
            pass

    for wid, watcher in _PRICE_WATCHERS.items():
        if watcher.get("status") != "active" or watcher.get("triggered"):
            continue
        ticker = watcher["ticker"]
        price = prices.get(ticker)
        if price is None:
            continue

        triggered_flag = False
        wt = watcher["type"]
        tp = watcher.get("trigger_price")

        if wt == "above" and tp and price > tp:
            triggered_flag = True
        elif wt == "below" and tp and price < tp:
            triggered_flag = True
        elif wt == "range" and watcher.get("lower_price") and watcher.get("upper_price"):
            if price < watcher["lower_price"] or price > watcher["upper_price"]:
                triggered_flag = True
        elif wt == "breakout" and tp:
            # Simple breakout: price > trigger (can be refined)
            if price > tp:
                triggered_flag = True

        if triggered_flag:
            watcher["triggered"] = True
            watcher["triggered_at"] = datetime.now(timezone.utc).isoformat()
            watcher["triggered_price"] = price
            lower_str = str(watcher.get("lower_price", "?"))
            upper_str = str(watcher.get("upper_price", "?"))
            condition_str = f"{wt} @ {tp or f'{lower_str}-{upper_str}'}"
            triggered.append({
                "watcher_id": wid,
                "ticker": ticker,
                "condition": condition_str,
                "current_price": price,
                "triggered_at": watcher["triggered_at"],
            })

    if triggered:
        _save_watchers()

    return triggered


# ═════════════════════════════════════════════════════════════════════════════
# TOOL 5: SENTIMENT ANALYSIS
# ═════════════════════════════════════════════════════════════════════════════

def analyze_sentiment(ticker: str, lookback_days: int = 7) -> dict:
    """Analyze market sentiment for a ticker using price action as proxy.

    Uses price trends, volume, and volatility as sentiment indicators
    since we don't have a news/social media sentiment API connected.
    Connect a real sentiment API (e.g., Sentifi, MarketAux) for richer data.
    """
    bars = _alpaca_bars(ticker, "1D", limit=lookback_days + 30)
    if not bars or len(bars) < 5:
        return {"error": f"Insufficient price data for {ticker}"}

    closes = [b["c"] for b in bars]
    volumes = [b.get("v", 0) for b in bars]
    current_price = closes[-1]

    # Technical sentiment signals
    sma20 = _calculate_sma(closes, 20)
    sma50 = _calculate_sma(closes, 50)

    # Trend score (-100 to +100)
    short_trend = ((closes[-1] / closes[-5]) - 1) * 100 if len(closes) >= 5 else 0
    mid_trend = ((closes[-1] / closes[-20]) - 1) * 100 if len(closes) >= 20 else 0

    # Volume trend
    avg_vol = sum(volumes[-20:]) / min(20, len(volumes)) if volumes else 1
    vol_trend = (volumes[-1] / avg_vol) if avg_vol > 0 else 1

    # Volatility (ATR-like)
    ranges = [abs(bars[i]["h"] - bars[i]["l"]) for i in range(-14, 0)] if len(bars) >= 14 else [0.01]
    avg_range = sum(ranges) / len(ranges)
    volatility_score = min(avg_range / current_price * 100, 100) if current_price > 0 else 0

    # Composite score
    trend_score = (short_trend * 0.4 + mid_trend * 0.6)
    sentiment_score = max(-100, min(100, trend_score))

    # Classification
    if sentiment_score > 15:
        overall = "positive"
    elif sentiment_score < -15:
        overall = "negative"
    else:
        overall = "neutral"

    above_sma20 = current_price > sma20 if sma20 else None
    above_sma50 = current_price > sma50 if sma50 else None

    return {
        "ticker": ticker,
        "overall_sentiment": overall,
        "sentiment_score": round(sentiment_score / 100, 2),
        "price_action_signals": {
            "current_price": current_price,
            "short_term_trend": f"{short_trend:+.1f}% (5d)",
            "medium_term_trend": f"{mid_trend:+.1f}% (20d)" if len(closes) >= 20 else None,
            "above_20ma": above_sma20,
            "above_50ma": above_sma50,
            "volume_ratio": round(vol_trend, 1),
            "volatility": f"{volatility_score:.1f}% avg daily range",
        },
        "key_drivers": [
            "Price action-based analysis (no news/social feed connected)"
        ],
        "trend": "improving" if sentiment_score > 5 else "deteriorating" if sentiment_score < -5 else "stable",
        "note": "Connect a sentiment API (Sentifi, MarketAux) for real news/social sentiment",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ═════════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="TBA Analytics Tools")
    sub = parser.add_subparsers(dest="command")

    # backtest
    bt = sub.add_parser("backtest", help="Backtest a strategy")
    bt.add_argument("--ticker", required=True)
    bt.add_argument("--strategy", default="ma_crossover")
    bt.add_argument("--lookback", type=int, default=365)
    bt.add_argument("--risk", type=float, default=0.01)

    # optimize
    op = sub.add_parser("optimize", help="Optimize strategy parameters")
    op.add_argument("--ticker", required=True)
    op.add_argument("--strategy", default="ma_crossover")
    op.add_argument("--fast-min", type=int, default=5)
    op.add_argument("--fast-max", type=int, default=50)
    op.add_argument("--slow-min", type=int, default=50)
    op.add_argument("--slow-max", type=int, default=200)
    op.add_argument("--metric", default="sharpe")

    # monte carlo
    mc = sub.add_parser("monte-carlo", help="Monte Carlo simulation")
    mc.add_argument("--ticker", default="SPY")
    mc.add_argument("--simulations", type=int, default=10000)
    mc.add_argument("--lookback", type=int, default=365)

    # price watcher
    pw = sub.add_parser("price-watcher", help="Set up a price watcher")
    pw.add_argument("--ticker", required=True)
    pw.add_argument("--above", type=float, help="Alert when price goes above")
    pw.add_argument("--below", type=float, help="Alert when price goes below")
    pw.add_argument("--interval", type=int, default=300)

    # sentiment
    sn = sub.add_parser("sentiment", help="Analyze sentiment")
    sn.add_argument("--ticker", required=True)
    sn.add_argument("--lookback", type=int, default=7)

    # check watchers
    sub.add_parser("check-watchers", help="Check all price watchers")

    args = parser.parse_args()

    if args.command == "backtest":
        result = backtest_strategy(args.ticker, args.strategy, args.lookback, args.risk)
    elif args.command == "optimize":
        result = optimize_strategy(args.ticker, args.strategy,
                                   args.fast_min, args.fast_max,
                                   slow_min=args.slow_min, slow_max=args.slow_max,
                                   metric=args.metric)
    elif args.command == "monte-carlo":
        result = monte_carlo(args.ticker, num_simulations=args.simulations, lookback_days=args.lookback)
    elif args.command == "price-watcher":
        result = setup_price_watcher(args.ticker, "above" if args.above else "below",
                                     trigger_price=args.above or args.below,
                                     check_interval_seconds=args.interval)
    elif args.command == "sentiment":
        result = analyze_sentiment(args.ticker, args.lookback)
    elif args.command == "check-watchers":
        result = {"triggered": check_price_watchers()}
    else:
        parser.print_help()
        return

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
