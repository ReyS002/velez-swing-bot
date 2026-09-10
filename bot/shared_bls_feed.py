from __future__ import annotations

import fcntl
import json
import os
import time
from collections.abc import Callable
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


class SharedBlsFeed:
    """Coordinate one BLS download across dashboard containers through a file lock."""

    SCHEMA_VERSION = 1

    def __init__(
        self,
        cache_file: str,
        *,
        request_fn: Callable[..., Any],
        timeout: float,
        cache_seconds: int,
        retry_delays: tuple[float, ...],
        fallback_template: str,
        now_fn: Callable[[], float] = time.time,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.path = Path(cache_file)
        self.request_fn = request_fn
        self.timeout = max(1.0, min(float(timeout), 15.0))
        self.cache_seconds = max(3600, int(cache_seconds))
        self.failure_cache_seconds = min(self.cache_seconds, 900)
        self.retry_delays = retry_delays or (0.0,)
        self.fallback_template = fallback_template
        self.now_fn = now_fn
        self.sleep_fn = sleep_fn

    @classmethod
    def from_environment(
        cls,
        *,
        request_fn: Callable[..., Any],
        timeout: float,
    ) -> SharedBlsFeed | None:
        cache_file = os.getenv("BLS_SHARED_CACHE_FILE", "").strip()
        if not cache_file:
            return None
        try:
            cache_seconds = int(os.getenv("BLS_SHARED_CACHE_SECONDS", "43200"))
        except ValueError:
            cache_seconds = 43200
        delays = []
        for value in os.getenv("BLS_FETCH_RETRY_DELAYS_SECONDS", "0,2,5").split(","):
            try:
                delays.append(max(0.0, min(float(value.strip()), 30.0)))
            except ValueError:
                continue
        try:
            feed_timeout = float(
                os.getenv("BLS_FEED_TIMEOUT_SECONDS", str(min(timeout, 5.0)))
            )
        except ValueError:
            feed_timeout = min(timeout, 5.0)
        return cls(
            cache_file,
            request_fn=request_fn,
            timeout=feed_timeout,
            cache_seconds=cache_seconds,
            retry_delays=tuple(delays[:4]),
            fallback_template=os.getenv(
                "BLS_CALENDAR_FALLBACK_URL_TEMPLATE",
                "https://www.bls.gov/schedule/{year}/{month:02d}_sched_list.htm",
            ),
        )

    def load(self, start: date, end: date, ics_url: str) -> dict:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        with lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                return self._load_locked(start, end, ics_url)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _load_locked(self, start: date, end: date, ics_url: str) -> dict:
        now = self.now_fn()
        cached = self._read()
        if cached and self._covers(cached, start, end) and self._fresh(cached, now):
            cache_status = (
                "failure_cached" if cached.get("kind") == "error" else "fresh"
            )
            return self._result(cached, cache_status)

        failures: list[str] = []
        request_headers = {
            "User-Agent": os.getenv(
                "BLS_HTTP_USER_AGENT",
                "TradingBullDesk/1.0 (+https://bullpilot.app)",
            ).strip(),
            "Accept": "text/calendar,text/html;q=0.9,*/*;q=0.8",
        }
        if cached and cached.get("kind") == "ics":
            if cached.get("etag"):
                request_headers["If-None-Match"] = str(cached["etag"])
            if cached.get("last_modified"):
                request_headers["If-Modified-Since"] = str(cached["last_modified"])

        for attempt, delay in enumerate(self.retry_delays, start=1):
            if delay:
                self.sleep_fn(delay)
            try:
                response = self.request_fn(
                    ics_url, timeout=self.timeout, headers=request_headers
                )
                status = int(getattr(response, "status_code", 0))
                if status == 304 and cached and cached.get("kind") == "ics":
                    cached["fetched_at"] = now
                    cached["attempts"] = attempt
                    self._write(cached)
                    return self._result(cached, "revalidated")
                text = str(getattr(response, "text", "") or "")
                if status == 200 and "BEGIN:VCALENDAR" in text:
                    headers = getattr(response, "headers", {}) or {}
                    record = {
                        "schema_version": self.SCHEMA_VERSION,
                        "kind": "ics",
                        "payload": text,
                        "source_url": ics_url,
                        "source_urls": [ics_url],
                        "fetched_at": now,
                        "attempts": attempt,
                        "etag": headers.get("ETag") or headers.get("etag"),
                        "last_modified": headers.get("Last-Modified")
                        or headers.get("last-modified"),
                    }
                    self._write(record)
                    return self._result(record, "refreshed")
                failures.append(f"http_{status}" if status else "invalid_response")
            except Exception as exc:
                failures.append(f"{type(exc).__name__}:{exc}")

        fallback_urls = self._fallback_urls(start, end)
        fallback_payloads: list[str] = []
        for url in fallback_urls:
            try:
                response = self.request_fn(
                    url, timeout=self.timeout, headers=request_headers
                )
                status = int(getattr(response, "status_code", 0))
                text = str(getattr(response, "text", "") or "")
                invalid = (
                    status != 200
                    or "Access Denied" in text
                    or "<html" not in text.lower()
                )
                if invalid:
                    failures.append(
                        f"fallback_http_{status}"
                        if status
                        else "fallback_invalid_response"
                    )
                    fallback_payloads = []
                    break
                fallback_payloads.append(text)
            except Exception as exc:
                failures.append(f"fallback_{type(exc).__name__}:{exc}")
                fallback_payloads = []
                break
        if fallback_payloads and len(fallback_payloads) == len(fallback_urls):
            record = {
                "schema_version": self.SCHEMA_VERSION,
                "kind": "html",
                "payload": "\n".join(fallback_payloads),
                "source_url": fallback_urls[0],
                "source_urls": fallback_urls,
                "fetched_at": now,
                "coverage_start": start.isoformat(),
                "coverage_end": end.isoformat(),
                "attempts": len(self.retry_delays),
                "failures": failures[-6:],
            }
            self._write(record)
            return self._result(record, "fallback")

        if cached and cached.get("payload") and self._covers(cached, start, end):
            cached["failures"] = failures[-6:]
            return self._result(cached, "stale")

        error = {
            "schema_version": self.SCHEMA_VERSION,
            "kind": "error",
            "payload": "",
            "source_url": ics_url,
            "source_urls": [ics_url, *fallback_urls],
            "fetched_at": now,
            "attempts": len(self.retry_delays),
            "failures": failures[-6:] or ["unavailable"],
        }
        self._write(error)
        return self._result(error, "failed")

    def _read(self) -> dict | None:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        if (
            not isinstance(value, dict)
            or value.get("schema_version") != self.SCHEMA_VERSION
        ):
            return None
        return value

    def _write(self, value: dict) -> None:
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(value, separators=(",", ":")) + "\n", encoding="utf-8"
        )
        temporary.chmod(0o644)
        os.replace(temporary, self.path)

    def _fresh(self, value: dict, now: float) -> bool:
        ttl = (
            self.failure_cache_seconds
            if value.get("kind") == "error"
            else self.cache_seconds
        )
        try:
            return now - float(value.get("fetched_at", 0)) < ttl
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _covers(value: dict, start: date, end: date) -> bool:
        if value.get("kind") in {"ics", "error"}:
            return True
        try:
            return (
                str(value["coverage_start"]) <= start.isoformat()
                and str(value["coverage_end"]) >= end.isoformat()
            )
        except KeyError:
            return False

    def _fallback_urls(self, start: date, end: date) -> list[str]:
        current = start.replace(day=1)
        limit = end.replace(day=1)
        urls = []
        while current <= limit and len(urls) < 6:
            urls.append(
                self.fallback_template.format(year=current.year, month=current.month)
            )
            current = date(
                current.year + (1 if current.month == 12 else 0),
                1 if current.month == 12 else current.month + 1,
                1,
            )
        return urls

    def _result(self, value: dict, cache_status: str) -> dict:
        fetched_at = value.get("fetched_at")
        try:
            fetched_iso = datetime.fromtimestamp(
                float(fetched_at), tz=timezone.utc
            ).isoformat()
        except (TypeError, ValueError, OSError):
            fetched_iso = ""
        failures = list(value.get("failures") or [])
        reason = failures[-1] if failures else None
        if value.get("kind") == "error" and not reason:
            reason = "unavailable"
        return {
            "ok": value.get("kind") != "error",
            "kind": value.get("kind"),
            "text": str(value.get("payload") or ""),
            "url": str(value.get("source_url") or ""),
            "urls": list(value.get("source_urls") or []),
            "shared": True,
            "cache_status": cache_status,
            "fallback": value.get("kind") == "html",
            "stale": cache_status == "stale",
            "fetched_at": fetched_iso,
            "attempts": int(value.get("attempts") or 0),
            "reason": reason,
        }
