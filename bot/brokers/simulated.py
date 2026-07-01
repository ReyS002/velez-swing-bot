from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from ..core.data import YFinanceDataProvider
from ..core.execution import ExecutionSimulator
from ..core.portfolio import Portfolio
from ..core.types import Fill, Order, OrderType, Position, Side


# ── SimBrokerConfig ────────────────────────────────────────────────


@dataclass
class SimBrokerConfig:
    starting_cash: float = 100_000.0
    slippage_bps: float = 1.0
    commission_per_share: float = 0.0
    commission_per_contract: float = 2.0
    timezone: str = "US/Eastern"
    data_dir: str = ""

    base_url: str = "sim://localhost"
    data_url: str = "sim://localhost/data"

    @classmethod
    def from_env(cls) -> "SimBrokerConfig":
        return cls(
            starting_cash=float(os.getenv("BULLPILOT_INITIAL_CASH",
                                os.getenv("VELEZ_INITIAL_CASH", "100000"))),
            slippage_bps=float(os.getenv("BULLPILOT_SLIPPAGE_BPS",
                                os.getenv("VELEZ_SLIPPAGE_BPS", "1.0"))),
        )


# ── Simulated Broker ───────────────────────────────────────────────


class SimulatedBroker:
    """Drop-in replacement for AlpacaPaperBroker using local simulation.

    No Alpaca account required. Uses yfinance for live prices (free),
    ExecutionSimulator for realistic fills, and a local SQLite journal
    for position/order persistence.

    Interface matches AlpacaPaperBroker exactly so the webhook server
    doesn't need to know which broker it's talking to.
    """

    def __init__(
        self, 
        config: Optional[SimBrokerConfig] = None,
        contract_multipliers: Optional[Dict[str, float]] = None,
    ) -> None:
        self.config = config or SimBrokerConfig.from_env()
        self._contract_multipliers = contract_multipliers or {}
        self._data_provider = YFinanceDataProvider()
        self._execution = ExecutionSimulator(
            slippage_bps=self.config.slippage_bps,
            commission_per_share=self.config.commission_per_share,
            commission_per_contract=self.config.commission_per_contract,
        )
        self._portfolio = Portfolio(cash=self.config.starting_cash)
        self._lock = threading.Lock()
        self._orders: List[dict] = []
        self._fills: List[dict] = []
        self._data_dir = Path(self.config.data_dir or os.path.join(os.getcwd(), "data"))
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._data_dir / "sim_journal.db"
        self._init_db()
        self._load_state()

    # ── DB persistence ──────────────────────────────────────────

    def _init_db(self) -> None:
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sim_orders (
                    id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    qty INTEGER NOT NULL,
                    order_type TEXT NOT NULL,
                    limit_price REAL,
                    stop_price REAL,
                    status TEXT NOT NULL DEFAULT 'filled',
                    filled_price REAL,
                    filled_at TEXT,
                    created_at TEXT NOT NULL,
                    reason TEXT DEFAULT '',
                    metadata_json TEXT DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sim_positions (
                    symbol TEXT PRIMARY KEY,
                    qty INTEGER NOT NULL,
                    entry_price REAL NOT NULL,
                    entry_time TEXT NOT NULL,
                    stop_price REAL DEFAULT 0.0,
                    initial_stop REAL DEFAULT 0.0,
                    risk_per_share REAL DEFAULT 0.0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sim_portfolio (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            conn.commit()

    def _load_state(self) -> None:
        with sqlite3.connect(str(self._db_path)) as conn:
            # Load orders
            rows = conn.execute(
                "SELECT * FROM sim_orders ORDER BY created_at DESC"
            ).fetchall()
            self._orders = [
                {
                    "id": r[0], "symbol": r[1], "side": r[2], "qty": r[3],
                    "type": r[4], "limit_price": r[5], "stop_price": r[6],
                    "status": r[7], "filled_avg_price": r[8], "filled_at": r[9],
                    "created_at": r[10], "reason": r[11],
                }
                for r in rows
            ]

            # Load positions
            pos_rows = conn.execute("SELECT * FROM sim_positions").fetchall()
            for r in pos_rows:
                self._portfolio.positions[r[0]] = Position(
                    symbol=r[0], qty=r[1],
                    entry_price=r[2],
                    entry_time=datetime.fromisoformat(r[3]),
                    stop_price=r[4], initial_stop=r[5],
                    risk_per_share=r[6],
                )

            # Load cash
            cash_row = conn.execute(
                "SELECT value FROM sim_portfolio WHERE key='cash'"
            ).fetchone()
            if cash_row:
                self._portfolio.cash = float(cash_row[0])

    def _save_state(self) -> None:
        with sqlite3.connect(str(self._db_path)) as conn:
            # Save orders
            conn.execute("DELETE FROM sim_orders")
            for o in self._orders[-500:]:  # keep last 500
                conn.execute(
                    """INSERT INTO sim_orders VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        o["id"], o["symbol"], o["side"], o["qty"],
                        o["type"], o.get("limit_price"), o.get("stop_price"),
                        o.get("status", "filled"), o.get("filled_avg_price"),
                        o.get("filled_at"), o["created_at"],
                        o.get("reason", ""),
                        json.dumps(o.get("metadata", {})),
                    ),
                )

            # Save positions
            conn.execute("DELETE FROM sim_positions")
            for sym, pos in self._portfolio.positions.items():
                conn.execute(
                    """INSERT INTO sim_positions VALUES (?,?,?,?,?,?,?)""",
                    (
                        sym, pos.qty, pos.entry_price,
                        pos.entry_time.isoformat(),
                        pos.stop_price, pos.initial_stop, pos.risk_per_share,
                    ),
                )

            # Save cash
            conn.execute("DELETE FROM sim_portfolio")
            conn.execute(
                "INSERT INTO sim_portfolio VALUES ('cash', ?)",
                (str(self._portfolio.cash),),
            )
            conn.commit()

    # ── Market data helper ──────────────────────────────────────

    def _get_current_price(self, symbol: str) -> float:
        """Get latest price from yfinance (free, no API key)."""
        try:
            end = datetime.now(ZoneInfo(self.config.timezone))
            start = end - timedelta(days=2)
            df = self._data_provider.get_bars(
                symbol=symbol,
                start=start,
                end=end,
                timeframe="1m",
                timezone=self.config.timezone,
            )
            if df.empty:
                raise RuntimeError(f"No market data for {symbol}")
            return float(df["close"].iloc[-1])
        except Exception:
            # Fallback: use last known fill price
            for o in self._orders:
                if o["symbol"] == symbol and o.get("filled_avg_price"):
                    return float(o["filled_avg_price"])
            raise RuntimeError(f"Cannot determine price for {symbol}")

    # ── AlpacaPaperBroker-compatible interface ──────────────────

    def is_configured(self) -> bool:
        """Always configured — no API keys needed."""
        return True

    def validate_connection(self) -> dict:
        """Test that we can fetch market data."""
        try:
            self._get_current_price("SPY")
            return {
                "ok": True,
                "account_status": "ACTIVE",
                "trading_blocked": False,
                "account_number_tail": "SIM",
                "paper": True,
            }
        except Exception as exc:
            return {"ok": False, "reason": str(exc)}

    def get_account(self) -> dict:
        equity = self._portfolio.equity(
            prices={s: self._get_current_price(s) for s in self._portfolio.positions},
            contract_multipliers=self._contract_multipliers,
        )
        return {
            "id": "sim-account",
            "account_number": "SIM-0001",
            "status": "ACTIVE",
            "currency": "USD",
            "cash": str(self._portfolio.cash),
            "portfolio_value": str(equity),
            "equity": str(equity),
            "buying_power": str(equity * 2),
            "trading_blocked": False,
        }

    def get_positions_raw(self) -> List[dict]:
        positions = []
        for sym, pos in self._portfolio.positions.items():
            if pos.qty == 0:
                continue
            try:
                current_price = self._get_current_price(sym)
            except Exception:
                current_price = pos.entry_price
            side = "long" if pos.qty > 0 else "short"
            market_value = abs(pos.qty) * current_price
            cost_basis = abs(pos.qty) * pos.entry_price
            unrealized_pl = (
                (current_price - pos.entry_price) * pos.qty
                if pos.qty > 0
                else (pos.entry_price - current_price) * abs(pos.qty)
            )
            positions.append({
                "asset_id": sym,
                "symbol": sym,
                "exchange": "SIM",
                "asset_class": "us_equity",
                "avg_entry_price": str(pos.entry_price),
                "qty": str(abs(pos.qty)),
                "side": side,
                "market_value": str(market_value),
                "cost_basis": str(cost_basis),
                "unrealized_pl": str(unrealized_pl),
                "unrealized_plpc": str(
                    unrealized_pl / cost_basis if cost_basis else 0
                ),
                "current_price": str(current_price),
                "lastday_price": str(current_price),
                "change_today": "0.0",
            })
        return positions

    def get_orders_raw(
        self,
        *,
        status: str = "open",
        limit: int = 100,
        direction: str = "desc",
        nested: bool = True,
        symbols: Optional[str] = None,
    ) -> List[dict]:
        orders = self._orders
        if status != "all":
            orders = [o for o in orders if o.get("status") == status]
        if symbols:
            sym_set = set(s.strip() for s in symbols.split(","))
            orders = [o for o in orders if o["symbol"] in sym_set]
        if direction == "desc":
            orders = list(reversed(orders))
        if limit:
            orders = orders[:limit]
        return orders

    def get_portfolio_history_raw(
        self, *, period: str = "1M", timeframe: str = "1D"
    ) -> dict:
        equity = self._portfolio.cash
        for sym in list(self._portfolio.positions.keys()):
            try:
                price = self._get_current_price(sym)
                pos = self._portfolio.positions[sym]
                mult = self._contract_multipliers.get(sym, 1.0)
                equity += pos.qty * price * mult
            except Exception:
                pass
        return {
            "timestamp": [int(time.time())],
            "equity": [equity],
            "profit_loss": [equity - self.config.starting_cash],
            "profit_loss_pct": [
                (equity - self.config.starting_cash) / self.config.starting_cash * 100
            ],
            "base_value": [self.config.starting_cash],
        }

    def get_activities_raw(
        self,
        *,
        activity_types: str = "FILL",
        after: Optional[str] = None,
        until: Optional[str] = None,
        direction: str = "desc",
        page_size: int = 100,
    ) -> List[dict]:
        activities = []
        for o in self._orders:
            if o.get("status") == "filled":
                act = {
                    "id": o["id"],
                    "activity_type": "FILL",
                    "transaction_time": o.get("filled_at", o["created_at"]),
                    "type": "fill",
                    "price": str(o.get("filled_avg_price", "0")),
                    "qty": str(o["qty"]),
                    "side": o["side"],
                    "symbol": o["symbol"],
                    "order_id": o["id"],
                }
                activities.append(act)
        if direction == "desc":
            activities = list(reversed(activities))
        return activities[:page_size]

    def get_calendar_raw(
        self, *, start: Optional[str] = None, end: Optional[str] = None
    ) -> List[dict]:
        """Return basic US market calendar — open every weekday."""
        today = datetime.now(ZoneInfo(self.config.timezone)).date()
        days = []
        for i in range(7):
            d = today + timedelta(days=i)
            if d.weekday() < 5:  # Mon-Fri
                days.append({
                    "date": d.isoformat(),
                    "open": f"{d.isoformat()}T09:30:00",
                    "close": f"{d.isoformat()}T16:00:00",
                    "session_open": "0930",
                    "session_close": "1600",
                })
        return days

    def get_positions(self) -> List[Position]:
        return list(self._portfolio.positions.values())

    def submit_order(self, order: Order) -> Fill:
        with self._lock:
            try:
                price = self._get_current_price(order.symbol)
            except Exception:
                price = order.limit_price or 100.0

            mult = self._contract_multipliers.get(order.symbol, 1.0)
            fill = self._execution.fill_at_price(
                order=order, price=price,
                timestamp=datetime.now(ZoneInfo(self.config.timezone)),
                contract_multiplier=mult,
            )
            self._portfolio.apply_fill(fill, mult)

            order_record = {
                "id": f"sim-{uuid.uuid4().hex[:16]}",
                "client_order_id": order.metadata.get("client_order_id", ""),
                "symbol": order.symbol,
                "side": order.side.value,
                "qty": order.qty,
                "type": order.order_type.value,
                "limit_price": order.limit_price,
                "stop_price": order.metadata.get("stop_price"),
                "status": "filled",
                "filled_avg_price": str(fill.price),
                "filled_at": fill.timestamp.isoformat(),
                "created_at": fill.timestamp.isoformat(),
                "reason": order.reason,
            }
            self._orders.append(order_record)
            self._save_state()

            return fill

    def submit_order_payload(self, payload: dict) -> dict:
        """Accept raw Alpaca-style payload and simulate fill."""
        side = Side.BUY if payload.get("side", "buy") == "buy" else Side.SELL
        order_type = (
            OrderType.LIMIT if payload.get("type") == "limit" else OrderType.MARKET
        )
        order = Order(
            symbol=payload["symbol"],
            side=side,
            qty=int(float(payload.get("qty", 0))),
            order_type=order_type,
            limit_price=(
                float(payload["limit_price"]) if payload.get("limit_price") else None
            ),
            timestamp=datetime.now(ZoneInfo(self.config.timezone)),
            reason=payload.get("client_order_id", ""),
            metadata={
                "client_order_id": payload.get("client_order_id", ""),
                "stop_price": (
                    float(payload["stop_loss"]["stop_price"])
                    if payload.get("stop_loss", {}).get("stop_price")
                    else None
                ),
            },
        )
        fill = self.submit_order(order)
        return {
            "id": self._orders[-1]["id"] if self._orders else "sim-unknown",
            "client_order_id": order.metadata.get("client_order_id", ""),
            "status": "filled",
            "filled_avg_price": str(fill.price),
            "filled_qty": str(order.qty),
            "symbol": order.symbol,
            "side": order.side.value,
        }

    def build_entry_payload(self, **kwargs) -> dict:
        return kwargs

    def cancel_all_orders(self) -> dict:
        return {"status": "ok", "cancelled": 0}

    def cancel_order(self, order_id: str) -> dict:
        return {"status": "ok", "id": order_id}

    def close(self) -> None:
        self._save_state()

    def _headers(self) -> dict:
        return {"Content-Type": "application/json"}

    def _request(self, method: str, path: str, **kwargs) -> Any:
        """Simulate Alpaca-style request routing."""
        if path == "/v2/account":
            return self.get_account()
        if path.startswith("/v2/positions"):
            return self.get_positions_raw()
        if path.startswith("/v2/orders"):
            return self.get_orders_raw()
        if path.startswith("/v2/account/portfolio/history"):
            return self.get_portfolio_history_raw()
        if path.startswith("/v2/account/activities"):
            return self.get_activities_raw()
        if path.startswith("/v2/calendar"):
            return self.get_calendar_raw()
        return {}

    def order_payload_from_order(self, order: Order, **kwargs) -> dict:
        return {"symbol": order.symbol, "qty": order.qty, "side": order.side.value}

    def _response_fill_price(self, response: dict, order: Order) -> float:
        return float(response.get("filled_avg_price", 0.0))

    def _price(self, price: float) -> str:
        return f"{float(price):.2f}"
