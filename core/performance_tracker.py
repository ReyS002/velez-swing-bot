"""
Performance Feedback Loop — tracks win rate per strategy.

Logs every trade signal + outcome to a local SQLite DB.
Reports on request. Never auto-disables — read-only tracking.

Schema:
  - id, timestamp, symbol, strategy, side, entry, stop, status (open/won/lost), pnl
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PERF_DB = Path("/app/data/performance_tracker.db")
PERF_KEY = "performance_tracker"


class PerformanceTracker:
    def __init__(self, config: dict, db_path: Optional[Path] = None) -> None:
        self.config = config.get(PERF_KEY, {})
        if not self.config.get("enabled", True):
            return  # still init but don't write
        self.db_path = db_path or PERF_DB
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    side TEXT NOT NULL,
                    entry_price REAL,
                    stop_price REAL,
                    target_price REAL,
                    status TEXT DEFAULT 'open',
                    pnl REAL,
                    exit_price REAL,
                    exit_reason TEXT,
                    metadata TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_strategy
                ON trades(strategy)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_status
                ON trades(status)
            """)

    def log_signal(self, symbol: str, strategy: str, side: str,
                   entry: Optional[float] = None, stop: Optional[float] = None,
                   target: Optional[float] = None,
                   metadata: Optional[dict] = None) -> None:
        if not self.config.get("enabled", True):
            return
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    """INSERT INTO trades
                       (timestamp, symbol, strategy, side, entry_price,
                        stop_price, target_price, status, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?)""",
                    (
                        datetime.now(timezone.utc).isoformat(),
                        symbol, strategy, side,
                        entry, stop, target,
                        json.dumps(metadata or {}),
                    ),
                )
        except Exception:
            pass  # silent — don't break trading for logging

    def close_trade(self, trade_id: int, pnl: float,
                    exit_price: float, reason: str = "manual") -> None:
        if not self.config.get("enabled", True):
            return
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    """UPDATE trades SET status='closed', pnl=?,
                       exit_price=?, exit_reason=? WHERE id=?""",
                    (pnl, exit_price, reason, trade_id),
                )
        except Exception:
            pass

    def win_rate(self, strategy: Optional[str] = None,
                 days: int = 30) -> Dict[str, Any]:
        """Return win rate stats. If strategy=None, returns aggregate."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                where = ""
                params: List[Any] = []
                if strategy:
                    where = "AND strategy = ?"
                    params.append(strategy)

                result = conn.execute(
                    f"""SELECT
                           COUNT(*) as total,
                           SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                           SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
                           AVG(CASE WHEN pnl IS NOT NULL THEN pnl ELSE NULL END) as avg_pnl,
                           strategy
                        FROM trades
                        WHERE status='closed'
                          AND created_at >= datetime('now', ?)
                          {where}
                        GROUP BY strategy
                        ORDER BY total DESC""",
                    [f"-{days} days"] + params,
                ).fetchall()

                total_trades = conn.execute(
                    "SELECT COUNT(*) FROM trades WHERE status='open'"
                ).fetchone()[0]

                return {
                    "strategies": [
                        {
                            "name": r[4],
                            "total": r[0],
                            "wins": r[1] or 0,
                            "losses": r[2] or 0,
                            "win_rate": round((r[1] or 0) / max(r[0], 1) * 100, 1),
                            "avg_pnl": round(r[3] or 0, 2),
                        }
                        for r in result
                    ],
                    "open_trades": total_trades,
                }
        except Exception:
            return {"strategies": [], "open_trades": 0}

    def summary(self) -> str:
        """Human-readable summary for dashboard/report."""
        data = self.win_rate()
        lines = [f"📊 Performance (30d) — {data['open_trades']} open trades"]
        for s in data["strategies"]:
            bar = "🟢" if s["win_rate"] >= 50 else "🔴"
            lines.append(
                f"  {bar} {s['name']}: {s['total']} trades, "
                f"{s['win_rate']}% win rate, "
                f"avg PnL ${s['avg_pnl']:.2f}"
            )
        if not data["strategies"]:
            lines.append("  No closed trades yet")
        return "\n".join(lines)
