from __future__ import annotations

from datetime import datetime
from typing import Dict, List

import math

from ..core.types import TradeRecord


def compute_metrics(trades: List[TradeRecord], initial_cash: float) -> Dict[str, float]:
    if not trades:
        return {
            "total_pnl": 0.0,
            "ending_equity": initial_cash,
            "win_rate": 0.0,
            "expectancy": 0.0,
            "max_drawdown": 0.0,
            "cagr": 0.0,
            "sharpe": 0.0,
        }

    trades = sorted(trades, key=lambda t: t.exit_time)
    total_pnl = sum(t.pnl for t in trades)
    ending_equity = initial_cash + total_pnl

    wins = [t for t in trades if t.pnl > 0]
    win_rate = len(wins) / len(trades) if trades else 0.0
    expectancy = total_pnl / len(trades) if trades else 0.0

    # Equity curve from trade exits
    equity = initial_cash
    peak = initial_cash
    max_dd = 0.0
    returns = []
    for t in trades:
        equity += t.pnl
        peak = max(peak, equity)
        dd = (equity - peak) / peak
        max_dd = min(max_dd, dd)
        returns.append(t.pnl / initial_cash)

    start = trades[0].entry_time
    end = trades[-1].exit_time
    days = max((end - start).days, 1)
    cagr = (ending_equity / initial_cash) ** (365 / days) - 1

    if len(returns) > 1:
        avg = sum(returns) / len(returns)
        variance = sum((r - avg) ** 2 for r in returns) / (len(returns) - 1)
        std = math.sqrt(variance)
        sharpe = (avg / std) * math.sqrt(len(returns)) if std > 0 else 0.0
    else:
        sharpe = 0.0

    return {
        "total_pnl": total_pnl,
        "ending_equity": ending_equity,
        "win_rate": win_rate,
        "expectancy": expectancy,
        "max_drawdown": abs(max_dd),
        "cagr": cagr,
        "sharpe": sharpe,
    }
