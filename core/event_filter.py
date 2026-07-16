"""
Event Calendar Filter — skip trading during high-impact events.

Checks for FOMC, CPI, earnings, and other major macro events.
Returns a "skip" flag if the current time is within the configured
window before/after an event.

Optional: config.flags can skip per event type.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    import urllib.request
    HAS_URL = True
except ImportError:
    HAS_URL = False

EVENT_KEY = "event_filter"

# ── Known upcoming major event dates (updated quarterly or via API) ──
# Format: (date, label, type)
# These serve as fallback if the API call fails

FALLBACK_EVENTS: List[Tuple[str, str, str]] = [
    # FOMC 2026 (remaining)
    ("2026-07-29", "FOMC Meeting", "fomc"),
    ("2026-09-17", "FOMC Meeting", "fomc"),
    ("2026-11-05", "FOMC Meeting", "fomc"),
    ("2026-12-16", "FOMC Meeting", "fomc"),
    # CPI releases
    ("2026-07-15", "CPI Release", "macro"),
    ("2026-08-12", "CPI Release", "macro"),
    ("2026-09-11", "CPI Release", "macro"),
    ("2026-10-14", "CPI Release", "macro"),
    ("2026-11-13", "CPI Release", "macro"),
    ("2026-12-11", "CPI Release", "macro"),
    # NFP / Jobs
    ("2026-08-07", "Jobs Report (NFP)", "macro"),
    ("2026-09-04", "Jobs Report (NFP)", "macro"),
    ("2026-10-02", "Jobs Report (NFP)", "macro"),
    ("2026-11-06", "Jobs Report (NFP)", "macro"),
    ("2026-12-04", "Jobs Report (NFP)", "macro"),
]


class EventFilter:
    """Check if trading should be paused due to upcoming economic events.

    Usage:
        ef = EventFilter(config)
        skip, reason = ef.should_skip()
        if skip:
            # pause trading
    """

    def __init__(self, config: dict) -> None:
        self.cfg = config.get(EVENT_KEY, {})
        self.enabled = self.cfg.get("enabled", True)
        self.skip_fomc = self.cfg.get("skip_fomc", True)
        self.skip_macro = self.cfg.get("skip_macro", True)
        self.skip_earnings = self.cfg.get("skip_earnings", False)  # off by default — needs symbol list
        self.window_before = int(self.cfg.get("window_minutes_before", 60))
        self.window_after = int(self.cfg.get("window_minutes_after", 30))
        self._fetched_events: List[Tuple[datetime, str, str]] = []
        self._last_fetch: Optional[datetime] = None

    def should_skip(self, symbol: Optional[str] = None) -> Tuple[bool, str]:
        """Check if trading should be skipped right now.

        Returns (skip, reason). If skip is True, reason explains why.
        """
        if not self.enabled:
            return False, ""

        now = datetime.now(timezone.utc)
        events = self._get_events()

        for event_dt, label, etype in events:
            start = event_dt - timedelta(minutes=self.window_before)
            end = event_dt + timedelta(minutes=self.window_after)

            if start <= now <= end:
                if etype == "fomc" and not self.skip_fomc:
                    continue
                if etype == "macro" and not self.skip_macro:
                    continue
                if etype == "earnings" and not self.skip_earnings:
                    continue

                return (True,
                        f"skip: {label} ({event_dt.strftime('%b %d %H:%M')}, "
                        f"{int((event_dt - now).total_seconds() // 60)}min away)")

        return False, ""

    def _get_events(self) -> List[Tuple[datetime, str, str]]:
        """Get upcoming events, trying API first then fallback."""
        now = datetime.now(timezone.utc)

        # Try federal reserve API for FOMC dates
        if HAS_URL and (self._last_fetch is None or
                        (now - self._last_fetch).total_seconds() > 3600):
            self._fetched_events = self._fetch_api_events()
            self._last_fetch = now

        if self._fetched_events:
            return [
                (dt, label, etype)
                for dt, label, etype in self._fetched_events
                if dt > now - timedelta(days=1)
            ]

        # Fallback to hardcoded events
        results = []
        for date_str, label, etype in FALLBACK_EVENTS:
            dt = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
            if dt > now - timedelta(days=1):
                # Default to 14:00 ET (18:00 UTC) for events
                dt = dt.replace(hour=18, minute=0)
                results.append((dt, label, etype))

        return results

    def _fetch_api_events(self) -> List[Tuple[datetime, str, str]]:
        """Fetch from federal reserve calendar API."""
        try:
            # Fed calendar API
            req = urllib.request.Request(
                "https://www.federalreserve.gov/json/calendar.json",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read().decode())
            events = []
            for item in data.get("events", []):
                title = item.get("title", "")
                date_str = item.get("date", "")
                if "FOMC" in title:
                    dt = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
                    events.append((dt, title, "fomc"))
            return events
        except Exception:
            return []
