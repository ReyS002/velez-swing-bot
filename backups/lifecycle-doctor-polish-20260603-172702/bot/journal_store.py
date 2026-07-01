from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _json_dumps(value: Any) -> str:
    return json.dumps(value or {}, default=str, sort_keys=True)


def _json_loads(value: Any, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return fallback


class JournalStore:
    """SQLite memory for Trading Bull Desk sessions.

    This is intentionally small and dependency-free so it works inside the VPS
    webhook container without adding another service.
    """

    def __init__(self, config: dict, db_path: Optional[str] = None) -> None:
        self.config = config
        self.path = Path(db_path or os.getenv("VELEZ_JOURNAL_DB", "") or self._default_path()).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self.seed_watchlist(config.get("symbols", []))

    def record_decision(self, snapshot: dict, order_payload: Optional[dict] = None, broker_response: Optional[dict] = None) -> None:
        timestamp = str(snapshot.get("timestamp") or _utc_now().isoformat())
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO decisions (
                    timestamp, alert_ref, status, reason, symbol, side, play, qty,
                    order_type, entry_price, stop_price, take_profit_price, timeframe,
                    location, max_dollar_risk, order_payload_json, broker_response_json, snapshot_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    snapshot.get("alert_ref"),
                    snapshot.get("status"),
                    snapshot.get("reason"),
                    snapshot.get("symbol"),
                    snapshot.get("side"),
                    snapshot.get("play"),
                    int(snapshot.get("qty") or 0),
                    snapshot.get("order_type"),
                    snapshot.get("entry_price"),
                    snapshot.get("stop_price"),
                    snapshot.get("take_profit_price"),
                    snapshot.get("timeframe"),
                    snapshot.get("location"),
                    snapshot.get("max_dollar_risk"),
                    _json_dumps(order_payload),
                    _json_dumps(broker_response),
                    _json_dumps(snapshot),
                ),
            )

        if snapshot.get("status") == "proposed" and order_payload and self._auto_stage_enabled():
            self.stage_order(snapshot, order_payload)

    def latest_decisions(self, limit: int = 80) -> List[dict]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT snapshot_json FROM decisions ORDER BY datetime(timestamp) DESC, id DESC LIMIT ?",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
        return [_json_loads(row["snapshot_json"], {}) for row in rows]

    def decision_by_alert_ref(self, alert_ref: str) -> Optional[dict]:
        cleaned = str(alert_ref or "").strip()
        if not cleaned:
            return None
        with self._connect() as db:
            row = db.execute(
                """
                SELECT timestamp, alert_ref, status, reason, symbol, side, play, qty,
                       order_type, entry_price, stop_price, take_profit_price, timeframe,
                       location, max_dollar_risk, snapshot_json
                FROM decisions
                WHERE alert_ref = ?
                ORDER BY datetime(timestamp) DESC, id DESC
                LIMIT 1
                """,
                (cleaned,),
            ).fetchone()
        return self._decision_row(row) if row else None

    def decision_entries(self, limit: int = 80, symbol: str = "", status: str = "") -> List[dict]:
        clauses: List[str] = []
        params: List[Any] = []
        cleaned_symbol = str(symbol or "").upper().strip()
        cleaned_status = str(status or "").lower().strip()
        if cleaned_symbol:
            clauses.append("symbol = ?")
            params.append(cleaned_symbol)
        if cleaned_status:
            clauses.append("LOWER(status) = ?")
            params.append(cleaned_status)
        sql = """
            SELECT timestamp, alert_ref, status, reason, symbol, side, play, qty,
                   order_type, entry_price, stop_price, take_profit_price, timeframe,
                   location, max_dollar_risk, snapshot_json
            FROM decisions
        """
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY datetime(timestamp) DESC, id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with self._connect() as db:
            rows = db.execute(sql, tuple(params)).fetchall()
        return [self._decision_row(row) for row in rows]

    def decisions_between(self, start_iso: str, end_iso: str, limit: int = 1000) -> List[dict]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT snapshot_json FROM decisions
                WHERE date(timestamp) >= date(?) AND date(timestamp) <= date(?)
                ORDER BY datetime(timestamp) DESC, id DESC
                LIMIT ?
                """,
                (start_iso, end_iso, max(1, min(int(limit), 5000))),
            ).fetchall()
        return [_json_loads(row["snapshot_json"], {}) for row in rows]

    def seed_watchlist(self, symbols: Iterable[dict]) -> None:
        now = _utc_now().isoformat()
        with self._connect() as db:
            for item in symbols:
                symbol = str(item.get("symbol", "")).upper().strip()
                if not symbol:
                    continue
                db.execute(
                    """
                    INSERT INTO watchlist (
                        symbol, asset_type, contract_multiplier, session, enabled, notes, source, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 1, ?, 'config', ?, ?)
                    ON CONFLICT(symbol) DO NOTHING
                    """,
                    (
                        symbol,
                        item.get("type", "equity"),
                        float(item.get("contract_multiplier", 1) or 1),
                        item.get("session", "rth"),
                        item.get("notes", ""),
                        now,
                        now,
                    ),
                )

    def list_watchlist(self, include_disabled: bool = False) -> List[dict]:
        sql = "SELECT * FROM watchlist"
        params: tuple[Any, ...] = ()
        if not include_disabled:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY symbol"
        with self._connect() as db:
            rows = db.execute(sql, params).fetchall()
        return [self._watchlist_row(row) for row in rows]

    def upsert_watchlist(self, item: dict) -> dict:
        symbol = str(item.get("symbol", "")).upper().strip().replace(" ", "")
        if not symbol:
            raise ValueError("symbol is required")
        asset_type = str(item.get("type") or item.get("asset_type") or "equity").lower()
        if asset_type not in {"equity", "stock", "future", "crypto", "forex"}:
            raise ValueError("asset_type must be equity, future, crypto, forex, or stock")
        try:
            contract_multiplier = float(item.get("contract_multiplier", 1) or 1)
        except (TypeError, ValueError) as exc:
            raise ValueError("contract_multiplier must be numeric") from exc
        if contract_multiplier <= 0:
            raise ValueError("contract_multiplier must be positive")
        session = str(item.get("session") or ("full" if asset_type == "future" else "rth"))
        notes = str(item.get("notes") or "")[:500]
        now = _utc_now().isoformat()
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO watchlist (
                    symbol, asset_type, contract_multiplier, session, enabled, notes, source, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 1, ?, 'dashboard', ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    asset_type = excluded.asset_type,
                    contract_multiplier = excluded.contract_multiplier,
                    session = excluded.session,
                    enabled = 1,
                    notes = excluded.notes,
                    updated_at = excluded.updated_at
                """,
                (symbol, asset_type, contract_multiplier, session, notes, now, now),
            )
        return self.get_watchlist_symbol(symbol) or {}

    def remove_watchlist(self, symbol: str) -> bool:
        cleaned = str(symbol or "").upper().strip()
        if not cleaned:
            return False
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE watchlist SET enabled = 0, updated_at = ? WHERE symbol = ?",
                (_utc_now().isoformat(), cleaned),
            )
        return cursor.rowcount > 0

    def get_watchlist_symbol(self, symbol: str) -> Optional[dict]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM watchlist WHERE symbol = ?", (str(symbol).upper().strip(),)).fetchone()
        return self._watchlist_row(row) if row else None

    def stage_order(self, snapshot: dict, order_payload: dict, ttl_minutes: Optional[int] = None) -> dict:
        existing = self.pending_orders_for_alert(str(snapshot.get("alert_ref") or ""))
        if existing:
            return existing[0]

        now = _utc_now()
        approval_id = uuid.uuid4().hex[:8].upper()
        ttl = ttl_minutes if ttl_minutes is not None else int(os.getenv("VELEZ_APPROVAL_TTL_MINUTES", "30"))
        expires_at = now + timedelta(minutes=max(1, min(ttl, 240)))
        phrase = f"APPROVE PAPER ORDER {approval_id}"
        pending = {
            "id": approval_id,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "status": "staged",
            "decision_alert_ref": snapshot.get("alert_ref"),
            "symbol": snapshot.get("symbol"),
            "side": snapshot.get("side"),
            "qty": int(snapshot.get("qty") or 0),
            "order_type": snapshot.get("order_type"),
            "entry_price": snapshot.get("entry_price"),
            "stop_price": snapshot.get("stop_price"),
            "take_profit_price": snapshot.get("take_profit_price"),
            "max_dollar_risk": snapshot.get("max_dollar_risk"),
            "approval_phrase": phrase,
            "order_payload": order_payload,
        }
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO pending_orders (
                    id, created_at, expires_at, status, decision_alert_ref, symbol, side, qty,
                    order_type, entry_price, stop_price, take_profit_price, max_dollar_risk,
                    approval_phrase, order_payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pending["id"],
                    pending["created_at"],
                    pending["expires_at"],
                    pending["status"],
                    pending["decision_alert_ref"],
                    pending["symbol"],
                    pending["side"],
                    pending["qty"],
                    pending["order_type"],
                    pending["entry_price"],
                    pending["stop_price"],
                    pending["take_profit_price"],
                    pending["max_dollar_risk"],
                    pending["approval_phrase"],
                    _json_dumps(order_payload),
                ),
            )
        return pending

    def pending_orders_for_alert(self, alert_ref: str) -> List[dict]:
        if not alert_ref:
            return []
        self.expire_pending_orders()
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM pending_orders WHERE decision_alert_ref = ? AND status = 'staged' ORDER BY datetime(created_at) DESC",
                (alert_ref,),
            ).fetchall()
        return [self._pending_row(row) for row in rows]

    def pending_orders(self, include_inactive: bool = False) -> List[dict]:
        self.expire_pending_orders()
        sql = "SELECT * FROM pending_orders"
        if not include_inactive:
            sql += " WHERE status = 'staged'"
        sql += " ORDER BY datetime(created_at) DESC LIMIT 50"
        with self._connect() as db:
            rows = db.execute(sql).fetchall()
        return [self._pending_row(row) for row in rows]

    def approve_pending_order(self, approval_id: str, phrase: str, broker: Any) -> dict:
        self.expire_pending_orders()
        pending = self.get_pending_order(approval_id)
        if not pending:
            return {"ok": False, "reason": "pending_order_not_found"}
        if pending["status"] != "staged":
            return {"ok": False, "reason": f"pending_order_{pending['status']}", "pending": pending}
        if self._normalize_phrase(phrase) != self._normalize_phrase(pending["approval_phrase"]):
            return {"ok": False, "reason": "approval_phrase_mismatch", "pending": self._public_pending(pending)}
        try:
            response = broker.submit_order_payload(pending["order_payload"])
        except Exception as exc:
            self._update_pending_status(pending["id"], "error", error=str(exc))
            return {"ok": False, "reason": f"broker_order_failed:{exc}", "pending": self._public_pending(pending)}
        self._update_pending_status(pending["id"], "submitted", broker_response=response)
        updated = self.get_pending_order(pending["id"]) or pending
        return {"ok": True, "status": "submitted", "pending": self._public_pending(updated), "broker_response": response}

    def get_pending_order(self, approval_id: str) -> Optional[dict]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM pending_orders WHERE id = ?", (str(approval_id).upper().strip(),)).fetchone()
        return self._pending_row(row) if row else None

    def expire_pending_orders(self) -> int:
        now = _utc_now().isoformat()
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE pending_orders SET status = 'expired', updated_at = ? WHERE status = 'staged' AND datetime(expires_at) < datetime(?)",
                (now, now),
            )
        return cursor.rowcount

    def public_pending_orders(self) -> List[dict]:
        return [self._public_pending(item) for item in self.pending_orders()]

    def save_research(self, topic: str, result: dict) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO research_notes (timestamp, topic, result_json) VALUES (?, ?, ?)",
                (_utc_now().isoformat(), str(topic or "")[:240], _json_dumps(result)),
            )

    def latest_research(self, limit: int = 10) -> List[dict]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT timestamp, topic, result_json FROM research_notes ORDER BY datetime(timestamp) DESC, id DESC LIMIT ?",
                (max(1, min(limit, 50)),),
            ).fetchall()
        return [
            {"timestamp": row["timestamp"], "topic": row["topic"], **_json_loads(row["result_json"], {})}
            for row in rows
        ]

    def save_replay(self, result: dict) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO replay_runs (timestamp, symbol, scenario, result_json) VALUES (?, ?, ?, ?)",
                (
                    _utc_now().isoformat(),
                    str(result.get("symbol") or "").upper().strip(),
                    str(result.get("scenario") or "custom")[:120],
                    _json_dumps(result),
                ),
            )

    def latest_replays(self, limit: int = 5) -> List[dict]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT timestamp, symbol, scenario, result_json FROM replay_runs ORDER BY datetime(timestamp) DESC, id DESC LIMIT ?",
                (max(1, min(limit, 25)),),
            ).fetchall()
        return [
            {
                "timestamp": row["timestamp"],
                "symbol": row["symbol"],
                "scenario": row["scenario"],
                **_json_loads(row["result_json"], {}),
            }
            for row in rows
        ]

    def save_lifecycle_snapshot(self, payload: dict) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO lifecycle_snapshots (timestamp, payload_json) VALUES (?, ?)",
                (str(payload.get("timestamp") or _utc_now().isoformat()), _json_dumps(payload)),
            )

    def latest_lifecycle_snapshot(self) -> Optional[dict]:
        with self._connect() as db:
            row = db.execute(
                "SELECT payload_json FROM lifecycle_snapshots ORDER BY datetime(timestamp) DESC, id DESC LIMIT 1"
            ).fetchone()
        return _json_loads(row["payload_json"], {}) if row else None

    def record_trade_outcome(self, outcome: dict) -> dict:
        timestamp = str(outcome.get("timestamp") or _utc_now().isoformat())
        payload = dict(outcome)
        payload["timestamp"] = timestamp
        with self._connect() as db:
            cursor = db.execute(
                """
                INSERT INTO trade_outcomes (
                    timestamp, alert_ref, symbol, status, r_multiple, pnl, notes, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    payload.get("alert_ref"),
                    str(payload.get("symbol") or "").upper().strip(),
                    payload.get("status"),
                    payload.get("r_multiple"),
                    payload.get("pnl"),
                    str(payload.get("notes") or "")[:1000],
                    _json_dumps(payload),
                ),
            )
        payload["id"] = cursor.lastrowid
        return payload

    def latest_trade_outcomes(self, limit: int = 20) -> List[dict]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT id, timestamp, alert_ref, symbol, status, r_multiple, pnl, notes, payload_json
                FROM trade_outcomes
                ORDER BY datetime(timestamp) DESC, id DESC
                LIMIT ?
                """,
                (max(1, min(int(limit), 100)),),
            ).fetchall()
        outcomes: List[dict] = []
        for row in rows:
            payload = _json_loads(row["payload_json"], {})
            payload.update(
                {
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "alert_ref": row["alert_ref"],
                    "symbol": row["symbol"],
                    "status": row["status"],
                    "r_multiple": row["r_multiple"],
                    "pnl": row["pnl"],
                    "notes": row["notes"],
                }
            )
            outcomes.append(payload)
        return outcomes

    def get_setting(self, key: str, default: Any = None) -> Any:
        cleaned = str(key or "").strip()
        if not cleaned:
            return default
        with self._connect() as db:
            row = db.execute("SELECT value_json FROM runtime_settings WHERE key = ?", (cleaned,)).fetchone()
        if not row:
            return default
        return _json_loads(row["value_json"], default)

    def set_setting(self, key: str, value: Any) -> Any:
        cleaned = str(key or "").strip()
        if not cleaned:
            raise ValueError("setting key is required")
        now = _utc_now().isoformat()
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO runtime_settings (key, value_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (cleaned, _json_dumps(value), now),
            )
        return value

    def _default_path(self) -> Path:
        data_dir = Path(os.getenv("VELEZ_DATA_DIR", "bot/data/runtime"))
        return data_dir / "trading_bull_desk.sqlite3"

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def _init_db(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    alert_ref TEXT,
                    status TEXT,
                    reason TEXT,
                    symbol TEXT,
                    side TEXT,
                    play TEXT,
                    qty INTEGER DEFAULT 0,
                    order_type TEXT,
                    entry_price TEXT,
                    stop_price TEXT,
                    take_profit_price TEXT,
                    timeframe TEXT,
                    location TEXT,
                    max_dollar_risk REAL,
                    order_payload_json TEXT,
                    broker_response_json TEXT,
                    snapshot_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_decisions_timestamp ON decisions(timestamp);
                CREATE INDEX IF NOT EXISTS idx_decisions_alert_ref ON decisions(alert_ref);
                CREATE INDEX IF NOT EXISTS idx_decisions_symbol ON decisions(symbol);

                CREATE TABLE IF NOT EXISTS watchlist (
                    symbol TEXT PRIMARY KEY,
                    asset_type TEXT NOT NULL DEFAULT 'equity',
                    contract_multiplier REAL NOT NULL DEFAULT 1,
                    session TEXT NOT NULL DEFAULT 'rth',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    notes TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'dashboard',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS pending_orders (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    updated_at TEXT,
                    submitted_at TEXT,
                    status TEXT NOT NULL DEFAULT 'staged',
                    decision_alert_ref TEXT,
                    symbol TEXT,
                    side TEXT,
                    qty INTEGER,
                    order_type TEXT,
                    entry_price TEXT,
                    stop_price TEXT,
                    take_profit_price TEXT,
                    max_dollar_risk REAL,
                    approval_phrase TEXT NOT NULL,
                    order_payload_json TEXT NOT NULL,
                    broker_response_json TEXT,
                    error TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_pending_status ON pending_orders(status);
                CREATE INDEX IF NOT EXISTS idx_pending_alert_ref ON pending_orders(decision_alert_ref);

                CREATE TABLE IF NOT EXISTS research_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    result_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_research_timestamp ON research_notes(timestamp);

                CREATE TABLE IF NOT EXISTS replay_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT,
                    scenario TEXT NOT NULL,
                    result_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_replay_timestamp ON replay_runs(timestamp);
                CREATE INDEX IF NOT EXISTS idx_replay_symbol ON replay_runs(symbol);

                CREATE TABLE IF NOT EXISTS lifecycle_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_lifecycle_timestamp ON lifecycle_snapshots(timestamp);

                CREATE TABLE IF NOT EXISTS trade_outcomes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    alert_ref TEXT,
                    symbol TEXT,
                    status TEXT,
                    r_multiple REAL,
                    pnl REAL,
                    notes TEXT,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_outcomes_timestamp ON trade_outcomes(timestamp);
                CREATE INDEX IF NOT EXISTS idx_outcomes_symbol ON trade_outcomes(symbol);
                CREATE INDEX IF NOT EXISTS idx_outcomes_alert_ref ON trade_outcomes(alert_ref);

                CREATE TABLE IF NOT EXISTS runtime_settings (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def _decision_row(self, row: sqlite3.Row) -> dict:
        snapshot = _json_loads(row["snapshot_json"], {})
        merged = {
            "timestamp": row["timestamp"],
            "alert_ref": row["alert_ref"],
            "status": row["status"],
            "reason": row["reason"],
            "symbol": row["symbol"],
            "side": row["side"],
            "play": row["play"],
            "qty": row["qty"],
            "order_type": row["order_type"],
            "entry_price": row["entry_price"],
            "stop_price": row["stop_price"],
            "take_profit_price": row["take_profit_price"],
            "timeframe": row["timeframe"],
            "location": row["location"],
            "max_dollar_risk": row["max_dollar_risk"],
        }
        merged.update({key: value for key, value in snapshot.items() if value not in (None, "")})
        return merged

    def _watchlist_row(self, row: sqlite3.Row) -> dict:
        return {
            "symbol": row["symbol"],
            "type": row["asset_type"],
            "contract_multiplier": row["contract_multiplier"],
            "session": row["session"],
            "enabled": bool(row["enabled"]),
            "notes": row["notes"],
            "source": row["source"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _pending_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "updated_at": row["updated_at"],
            "submitted_at": row["submitted_at"],
            "status": row["status"],
            "decision_alert_ref": row["decision_alert_ref"],
            "symbol": row["symbol"],
            "side": row["side"],
            "qty": row["qty"],
            "order_type": row["order_type"],
            "entry_price": row["entry_price"],
            "stop_price": row["stop_price"],
            "take_profit_price": row["take_profit_price"],
            "max_dollar_risk": row["max_dollar_risk"],
            "approval_phrase": row["approval_phrase"],
            "order_payload": _json_loads(row["order_payload_json"], {}),
            "broker_response": _json_loads(row["broker_response_json"], {}),
            "error": row["error"],
        }

    def _public_pending(self, item: dict) -> dict:
        return {
            key: value
            for key, value in item.items()
            if key not in {"order_payload", "broker_response", "error"} or key == "error" and value
        }

    def _update_pending_status(
        self,
        approval_id: str,
        status: str,
        *,
        broker_response: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> None:
        now = _utc_now().isoformat()
        submitted_at = now if status == "submitted" else None
        with self._connect() as db:
            db.execute(
                """
                UPDATE pending_orders
                SET status = ?, updated_at = ?, submitted_at = COALESCE(?, submitted_at),
                    broker_response_json = COALESCE(?, broker_response_json),
                    error = COALESCE(?, error)
                WHERE id = ?
                """,
                (
                    status,
                    now,
                    submitted_at,
                    _json_dumps(broker_response) if broker_response is not None else None,
                    error,
                    approval_id,
                ),
            )

    def _normalize_phrase(self, value: str) -> str:
        return " ".join(str(value or "").upper().split())

    def _auto_stage_enabled(self) -> bool:
        return os.getenv("VELEZ_AUTO_STAGE_PROPOSED_ORDERS", "true").strip().lower() in {"1", "true", "yes", "on"}
