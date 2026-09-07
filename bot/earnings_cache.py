"""A durable, process-locked public earnings calendar shared by desk editions."""
from __future__ import annotations

import csv
import fcntl
import hashlib
import io
import json
import os
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


def earnings_key() -> str:
    return next((os.getenv(name, "").strip() for name in (
        "ALPHA_VANTAGE_API_KEY", "ALPHAVANTAGE_API_KEY", "AV_API_KEY", "ALPHA_VINTAGE_API_KEY"
    ) if os.getenv(name, "").strip()), "")


class EarningsCalendarCache:
    refresh_seconds = 12 * 60 * 60
    retry_seconds = 30 * 60

    def __init__(self, *, path=None, key=None, session=requests, clock=time.time):
        self.key = earnings_key() if key is None else key
        key_scope = hashlib.sha256(self.key.encode()).hexdigest()[:16]
        self.path = Path(path or os.getenv("DESK_EARNINGS_CACHE_PATH") or
                         Path(tempfile.gettempdir()) / f"bull-earnings-{key_scope}.json")
        self.session, self.clock = session, clock
        self._stop = threading.Event()
        self._thread = None

    def _read(self) -> dict:
        try:
            value = json.loads(self.path.read_text())
            if value.get("version") == 1 and isinstance(value.get("items"), list) and all(isinstance(value.get(k, 0), (int, float)) for k in ("last_success", "last_attempt")) and all(isinstance(r, dict) and isinstance(r.get("symbol"), str) and isinstance(r.get("date"), str) for r in value["items"]):
                return value
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        return {"version": 1, "items": [], "last_success": 0, "last_attempt": 0}

    def _write(self, value: dict) -> None:
        fd, name = tempfile.mkstemp(prefix=self.path.name + ".", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(value, stream, separators=(",", ":"))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def refresh(self) -> dict:
        """At most one attempt per interval across workers; never discard valid rows."""
        if not self.key:
            return self.payload()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(str(self.path) + ".lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            cached = self._read()
            now = self.clock()
            success, attempt = cached.get("last_success", 0), cached.get("last_attempt", 0)
            if (success and now - success < self.refresh_seconds) or (attempt and now - attempt < self.retry_seconds):
                return self.payload(cached)
            cached["last_attempt"] = now
            try:
                response = self.session.get(
                    "https://www.alphavantage.co/query",
                    params={"function": "EARNINGS_CALENDAR", "horizon": "3month", "apikey": self.key},
                    timeout=(5, 20),
                )
                if response.status_code != 200:
                    raise ValueError("provider_http_error")
                raw = response.text.strip()
                if raw.startswith("{"):
                    value = json.loads(raw)
                    raise ValueError("provider_limit_or_key_error" if any(k in value for k in ("Information", "Note", "Error Message")) else "invalid_calendar")
                reader = csv.DictReader(io.StringIO(raw))
                if not {"symbol", "reportDate"}.issubset(reader.fieldnames or []):
                    raise ValueError("invalid_calendar")
                rows = []
                for row in reader:
                    symbol, day = str(row.get("symbol", "")).upper().strip(), str(row.get("reportDate", "")).strip()
                    try:
                        datetime.strptime(day, "%Y-%m-%d")
                    except ValueError:
                        continue
                    if symbol:
                        rows.append({"symbol": symbol, "date": day, "name": row.get("name") or symbol,
                                     "fiscal_date_ending": row.get("fiscalDateEnding") or "",
                                     "estimate": row.get("estimate") or "", "currency": row.get("currency") or "USD",
                                     "title": f"{symbol} earnings", "source": "Alpha Vantage", "time": "", "time_status": "not_provided"})
                if not rows:
                    raise ValueError("invalid_calendar")
                cached.update(items=sorted(rows, key=lambda r: (r["date"], r["symbol"])), last_success=now, error=None)
            except requests.RequestException:
                cached["error"] = "provider_unreachable"
            except (ValueError, TypeError) as exc:
                cached["error"] = str(exc) if str(exc) in {"provider_http_error", "provider_limit_or_key_error", "invalid_calendar"} else "invalid_calendar"
            self._write(cached)
            return self.payload(cached)

    def payload(self, cached=None) -> dict:
        cached = self._read() if cached is None else cached
        success = cached.get("last_success", 0)
        stale = not success or self.clock() - success >= self.refresh_seconds
        return {"items": cached["items"], "source": {
            "name": "Alpha Vantage Earnings Calendar", "configured": bool(self.key or success),
            "ok": bool(success) and not stale and not cached.get("error"), "stale": stale,
            "reason": cached.get("error") or ("awaiting_refresh" if self.key else "missing_api_key") if not success or cached.get("error") else ("stale_cache" if stale else "ready"),
            "as_of": datetime.fromtimestamp(success, timezone.utc).isoformat() if success else None,
            "next_refresh": datetime.fromtimestamp(success + self.refresh_seconds, timezone.utc).isoformat() if success else None,
            "total_records": len(cached["items"]), "shared": True,
        }}

    def start(self):
        if not self.key or self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        def run():
            while not self._stop.is_set():
                try:
                    self.refresh()
                except OSError:
                    pass  # Requests continue to expose the last readable cache state.
                self._stop.wait(60)
        self._thread = threading.Thread(target=run, name="shared-earnings-calendar", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
