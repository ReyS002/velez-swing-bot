"""
Capitol Conviction — Congressional Trading Overlay for Velez Bot.
Queries Capitol Trades DB for congressional activity on a given ticker
and computes a conviction score (0–100) that feeds into the confidence receipt.

Score breakdown:
  - Recent buy from committee chair: +25
  - Recent buy from senator/rep: +15
  - Multiple politicians buying (herd): +10 per extra pol
  - Recent sale by anyone: -20
  - Sale by known good trader (top 10%): -35
  - Stale data (>180 days): halve all scores
  - No data: neutral (0)
"""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict
from typing import Optional

DB_PATH = Path("/app/data/capitol_trades.db")

# Known high-performing politicians (by historical hit rate — seed list,
# will be replaced by ML scoring in Tier 2)
STRONG_TRADERS = {
    "Nancy Pelosi", "Daniel Goldman", "Josh Gottheimer", "Mark Green",
    "Michael McCaul", "John Boozman", "Kathy Manning",
}

# Committee chairs (more likely to have material non-public info in their domain)
COMMITTEE_CHAIRS = {
    "Nancy Pelosi", "Michael McCaul", "Mark Green", "Patrick McHenry",
    "Maxine Waters", "Garret Graves", "Frank Lucas",
}

RECENCY_WINDOW_DAYS = 180
HERD_THRESHOLD = 3  # politicians


def _connect() -> sqlite3.Connection:
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    return db


def get_capitol_conviction(symbol: str) -> dict:
    """
    Return congressional conviction data for a ticker.

    Returns dict with:
      - score: int (-50 to +100, where negative = bearish, 0 = neutral)
      - signals: list of human-readable signal descriptions
      - trade_count: total trades for this ticker in DB
      - latest_date: most recent trade date
      - buy_pct: percentage of trades that are buys
    """
    if not DB_PATH.exists():
        return _neutral("DB not found")

    db = _connect()

    # All trades for this symbol
    trades = db.execute(
        "SELECT * FROM trades WHERE ticker = ? ORDER BY transaction_date DESC",
        (symbol.upper(),),
    ).fetchall()

    if not trades:
        db.close()
        return _neutral(f"no congressional trades for {symbol}")

    now = datetime.now(timezone.utc)
    recent_cutoff = (now - timedelta(days=RECENCY_WINDOW_DAYS)).strftime("%Y-%m-%d")

    # Separate recent vs stale
    recent = [t for t in trades if t["transaction_date"] >= recent_cutoff]
    stale = len(trades) - len(recent)
    is_stale = len(recent) == 0

    # Compute signals
    signals = []
    score = 0

    for t in recent:
        name = t["politician_name"]
        tx_type = (t["transaction_type"] or "").lower()
        is_buy = "purchase" in tx_type
        is_sale = "sale" in tx_type
        is_chair = name in COMMITTEE_CHAIRS
        is_strong = name in STRONG_TRADERS

        if is_buy:
            if is_chair:
                score += 25
                signals.append(f"{name} (chair) bought {symbol}")
            elif is_strong:
                score += 20
                signals.append(f"{name} (strong) bought {symbol}")
            else:
                score += 15
                signals.append(f"{name} bought {symbol}")
        elif is_sale:
            if is_strong:
                score -= 35
                signals.append(f"{name} (strong) SOLD {symbol}")
            else:
                score -= 20
                signals.append(f"{name} sold {symbol}")

    # Herd bonus: multiple unique politicians buying same ticker
    recent_buyers = {
        t["politician_name"]
        for t in recent
        if "purchase" in (t["transaction_type"] or "").lower()
    }
    if len(recent_buyers) >= HERD_THRESHOLD:
        extra = (len(recent_buyers) - 2) * 10
        score += extra
        signals.append(
            f"🐂 HERD: {len(recent_buyers)} politicians buying {symbol} (+{extra})"
        )

    # Stale penalty
    if is_stale:
        score = score // 2
        signals.append(f"⚠️ data stale — no trades in {RECENCY_WINDOW_DAYS}d")

    # Clamp
    score = max(-50, min(100, score))

    # Buy percentage
    buy_count = sum(
        1 for t in trades if "purchase" in (t["transaction_type"] or "").lower()
    )
    buy_pct = buy_count / len(trades) if trades else 0

    db.close()

    return {
        "score": score,
        "signals": signals[:6],  # top 6
        "trade_count": len(trades),
        "latest_date": trades[0]["transaction_date"],
        "buy_pct": round(buy_pct, 2),
        "recent_trades": len(recent),
        "stale_trades": stale,
        "source": "capitol-trades-db",
    }


def _neutral(reason: str) -> dict:
    return {
        "score": 0,
        "signals": [reason],
        "trade_count": 0,
        "latest_date": None,
        "buy_pct": 0,
        "recent_trades": 0,
        "stale_trades": 0,
        "source": "capitol-trades-db",
    }
