from __future__ import annotations

import csv
import io
import json
import os
import re
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from html import unescape
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

import requests


MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
MONTH_PATTERN = "|".join(month.title() for month in MONTHS)
DATE_WORD_RE = re.compile(
    rf"\b(?P<month>{MONTH_PATTERN})\s+"
    r"(?P<day>\d{1,2})(?:st|nd|rd|th)?"
    r"(?:\s*[-–]\s*(?P<end_day>\d{1,2})(?:st|nd|rd|th)?)?"
    r"(?:,?\s*(?P<year>20\d{2}))?\b",
    re.IGNORECASE,
)
ISO_DATE_RE = re.compile(r"\b(?P<year>20\d{2})-(?P<month>\d{1,2})-(?P<day>\d{1,2})\b")
US_DATE_RE = re.compile(r"\b(?P<month>\d{1,2})/(?P<day>\d{1,2})/(?P<year>20\d{2})\b")
TIME_RE = re.compile(r"\b(?P<time>\d{1,2}:\d{2}\s*(?:AM|PM|A\.M\.|P\.M\.))\b", re.IGNORECASE)


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _first_env(names: Iterable[str]) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def _safe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _zone(name: str) -> ZoneInfo:
    aliases = {"US/Eastern": "America/New_York", "EST": "America/New_York"}
    try:
        return ZoneInfo(aliases.get(name, name) or "America/New_York")
    except Exception:
        return ZoneInfo("America/New_York")


class CalendarFeedService:
    """Builds the dashboard calendar from broker, journal, earnings, and macro feeds."""

    def __init__(
        self,
        broker: Any,
        config: dict,
        recent_decisions: Deque[dict],
        *,
        journal: Any = None,
        now_fn: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.broker = broker
        self.config = config
        self.recent_decisions = recent_decisions
        self.journal = journal
        self.now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self.timeout = _float_env("CALENDAR_FEED_TIMEOUT_SECONDS", 8.0)
        self.cache_seconds = _int_env("CALENDAR_FEED_CACHE_SECONDS", 21600)
        self.lookahead_days = _int_env("CALENDAR_EVENT_LOOKAHEAD_DAYS", 45)
        self.tz = _zone(str(config.get("timezone", "America/New_York")))
        self._cache: Dict[str, tuple[float, Any]] = {}

    def month_payload(self) -> dict:
        now = self.now_fn()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now_local = now.astimezone(self.tz)
        start = now_local.date().replace(day=1)
        end = self._month_end(start)
        today = now_local.date()
        event_end = max(end, today + timedelta(days=max(7, self.lookahead_days)))

        pnl = self._alpaca_pnl(start, end)
        alerts = self._alerts(start, end)
        sessions = self._alpaca_sessions(start, end, today)
        earnings = self._earnings(today, event_end)
        macro = self._macro_events(today, event_end)
        timeline = self._combined_timeline(
            today=today,
            sessions=sessions["items"],
            earnings=earnings["items"],
            events=macro["items"],
            alerts=alerts,
        )

        return {
            "ok": True,
            "timestamp": now_local.isoformat(),
            "range": {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "lookahead_end": event_end.isoformat(),
                "month_label": now_local.strftime("%B %Y"),
                "timezone": str(self.tz),
            },
            "pnl": pnl["data"],
            "alerts": alerts,
            "session": sessions["today"],
            "sessions": sessions["items"],
            "earnings": earnings["items"],
            "events": macro["items"],
            "timeline": timeline,
            "today": {
                "date": today.isoformat(),
                "session": sessions["today"],
                "events": [item for item in macro["items"] if item.get("date") == today.isoformat()],
                "earnings": [item for item in earnings["items"] if item.get("date") == today.isoformat()],
                "alerts": alerts["by_day"].get(today.isoformat(), 0),
            },
            "journal": {
                "status": "Ready for monthly review" if alerts["count"] else "No alerts logged this month",
                "sessions_logged": len(alerts["by_day"]),
                "recent_count": alerts["count"],
            },
            "sources": {
                "alpaca_pnl": pnl["source"],
                "alpaca_calendar": sessions["source"],
                "alpha_vantage": earnings["source"],
                "macro": macro["sources"],
            },
        }

    def _combined_timeline(self, *, today: date, sessions: List[dict], earnings: List[dict], events: List[dict], alerts: dict) -> List[dict]:
        items: List[dict] = []
        for item in events:
            items.append(
                {
                    "date": item.get("date"),
                    "time": item.get("time", ""),
                    "title": item.get("title", "Macro event"),
                    "kind": "macro",
                    "source": item.get("source", ""),
                    "importance": item.get("importance", "medium"),
                    "url": item.get("url", ""),
                }
            )
        for item in earnings:
            items.append(
                {
                    "date": item.get("date"),
                    "time": item.get("time", ""),
                    "title": f"{item.get('symbol', '')} earnings".strip(),
                    "kind": "earnings",
                    "source": item.get("source", "Alpha Vantage"),
                    "importance": "high",
                    "symbol": item.get("symbol"),
                    "name": item.get("name", ""),
                }
            )
        for item in sessions:
            session_date = item.get("date")
            if session_date and session_date >= today.isoformat():
                items.append(
                    {
                        "date": session_date,
                        "time": item.get("open", ""),
                        "title": item.get("label", "Regular market session"),
                        "kind": "session",
                        "source": "Alpaca",
                        "importance": "normal",
                    }
                )
        for alert_date, count in (alerts.get("by_day") or {}).items():
            if count:
                items.append(
                    {
                        "date": alert_date,
                        "time": "",
                        "title": f"{count} bot alert{'s' if count != 1 else ''} logged",
                        "kind": "journal",
                        "source": "Trading Bull Desk",
                        "importance": "normal",
                    }
                )
        items = [item for item in items if item.get("date")]
        items.sort(key=lambda item: (str(item.get("date")), str(item.get("time") or ""), self._timeline_rank(item)))
        return items[:48]

    def _timeline_rank(self, item: dict) -> int:
        ranks = {"macro": 0, "earnings": 1, "session": 2, "journal": 3}
        return ranks.get(str(item.get("kind")), 9)

    def _alpaca_pnl(self, start: date, end: date) -> dict:
        source = {"name": "Alpaca", "configured": self._broker_configured(), "ok": False}
        data = {
            "month_pl": 0.0,
            "unrealized_pl": 0.0,
            "equity_change": 0.0,
            "equity_first": None,
            "equity_last": None,
            "source": "alpaca",
            "detail": "Alpaca credentials are not configured",
        }
        if not source["configured"]:
            source["reason"] = "missing_credentials"
            return {"data": data, "source": source}

        errors: List[str] = []
        try:
            positions = self.broker.get_positions_raw()
            data["unrealized_pl"] = round(
                sum(_safe_float(item.get("unrealized_pl")) or 0.0 for item in positions if isinstance(item, dict)),
                2,
            )
        except Exception as exc:
            errors.append(f"positions:{exc}")

        try:
            history = self.broker.get_portfolio_history_raw(period="1M", timeframe="1D")
            equities = [_safe_float(value) for value in history.get("equity", []) if _safe_float(value) is not None]
            profit_loss = [_safe_float(value) for value in history.get("profit_loss", []) if _safe_float(value) is not None]
            if len(equities) >= 2:
                data["equity_first"] = round(float(equities[0]), 2)
                data["equity_last"] = round(float(equities[-1]), 2)
                data["equity_change"] = round(float(equities[-1]) - float(equities[0]), 2)
                data["month_pl"] = data["equity_change"]
                data["detail"] = f"Portfolio history, {start.isoformat()} to {end.isoformat()}"
            elif profit_loss:
                data["month_pl"] = round(float(profit_loss[-1]), 2)
                data["equity_change"] = data["month_pl"]
                data["detail"] = "Portfolio history profit/loss"
            else:
                data["detail"] = "Portfolio history returned no equity points"
        except Exception as exc:
            errors.append(f"portfolio_history:{exc}")

        source["ok"] = not errors or data["equity_last"] is not None or data["unrealized_pl"] != 0
        if errors:
            source["errors"] = errors[:3]
            if data["detail"].startswith("Alpaca credentials"):
                data["detail"] = "Alpaca calendar/P&L check needs attention"
        return {"data": data, "source": source}

    def _alpaca_sessions(self, start: date, end: date, today: date) -> dict:
        source = {"name": "Alpaca Market Calendar", "configured": self._broker_configured(), "ok": False}
        if not source["configured"]:
            source["reason"] = "missing_credentials"
            return {"items": [], "today": {"status": "Unknown", "label": "Alpaca calendar unavailable"}, "source": source}

        cache_key = f"alpaca_sessions:{start.isoformat()}:{end.isoformat()}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        items: List[dict] = []
        try:
            raw_sessions = self.broker.get_calendar_raw(start=start.isoformat(), end=end.isoformat())
            for item in raw_sessions:
                session_date = str(item.get("date", ""))
                if not session_date:
                    continue
                items.append(
                    {
                        "date": session_date,
                        "open": str(item.get("open", "")),
                        "close": str(item.get("close", "")),
                        "label": self._session_label(item),
                    }
                )
            items.sort(key=lambda item: item["date"])
            source["ok"] = True
            source["count"] = len(items)
        except Exception as exc:
            source["reason"] = str(exc)
            result = {"items": [], "today": {"status": "Unknown", "label": "Alpaca calendar check failed"}, "source": source}
            self._cache_set(cache_key, result)
            return result

        today_text = today.isoformat()
        today_session = next((item for item in items if item["date"] == today_text), None)
        next_session = next((item for item in items if item["date"] >= today_text), None)
        if today_session:
            today_status = {"status": "Open day", "label": today_session["label"], "date": today_text}
        elif next_session:
            today_status = {"status": "Closed today", "label": f"Next: {next_session['date']} {next_session['label']}", "date": today_text}
        else:
            today_status = {"status": "Unknown", "label": "No future session found", "date": today_text}

        result = {"items": items, "today": today_status, "source": source}
        self._cache_set(cache_key, result)
        return result

    def _alerts(self, start: date, end: date) -> dict:
        by_day: Counter[str] = Counter()
        recent: List[dict] = []
        decisions = list(self.recent_decisions)
        if self.journal is not None:
            try:
                decisions = self.journal.decisions_between(start.isoformat(), end.isoformat())
            except Exception:
                decisions = list(self.recent_decisions)
        for decision in decisions:
            timestamp = self._parse_datetime(decision.get("timestamp"))
            if not timestamp:
                continue
            local_day = timestamp.astimezone(self.tz).date()
            if start <= local_day <= end:
                by_day[local_day.isoformat()] += 1
                if len(recent) < 8:
                    recent.append(
                        {
                            "timestamp": timestamp.isoformat(),
                            "symbol": decision.get("symbol"),
                            "status": decision.get("status"),
                            "play": decision.get("play"),
                            "side": decision.get("side"),
                        }
                    )
        return {
            "count": sum(by_day.values()),
            "by_day": dict(sorted(by_day.items())),
            "recent": recent,
            "source": "session_journal",
        }

    def _earnings(self, start: date, end: date) -> dict:
        key = _first_env(("ALPHA_VANTAGE_API_KEY", "ALPHAVANTAGE_API_KEY", "AV_API_KEY", "ALPHA_VINTAGE_API_KEY"))
        symbols = self._equity_symbols()
        source = {
            "name": "Alpha Vantage Earnings Calendar",
            "configured": bool(key),
            "ok": False,
            "symbols": symbols,
        }
        if not key:
            source["reason"] = "missing_api_key"
            return {"items": [], "source": source}
        if not symbols:
            source["ok"] = True
            source["reason"] = "no_equity_symbols"
            return {"items": [], "source": source}

        cache_key = f"alpha_earnings:{start.isoformat()}:{end.isoformat()}:{','.join(symbols)}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        items: List[dict] = []
        errors: List[str] = []
        for symbol in symbols:
            try:
                response = requests.get(
                    "https://www.alphavantage.co/query",
                    params={"function": "EARNINGS_CALENDAR", "symbol": symbol, "horizon": "3month", "apikey": key},
                    timeout=self.timeout,
                )
                if response.status_code >= 400:
                    errors.append(f"{symbol}:http_{response.status_code}")
                    continue
                items.extend(self._parse_alpha_earnings(symbol, response.text, start, end))
            except requests.RequestException as exc:
                errors.append(f"{symbol}:{exc}")

        items = self._dedupe_events(items, ("date", "symbol", "title"))[:24]
        source["ok"] = bool(items) or not errors
        source["count"] = len(items)
        if errors:
            source["errors"] = errors[:5]
        result = {"items": items, "source": source}
        self._cache_set(cache_key, result)
        return result

    def _macro_events(self, start: date, end: date) -> dict:
        if not _bool_env("CALENDAR_MACRO_FEEDS_ENABLED", True):
            return {
                "items": [],
                "sources": [{"name": "Macro feeds", "configured": False, "ok": False, "reason": "disabled"}],
            }

        cache_key = f"macro_events:{start.isoformat()}:{end.isoformat()}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        feeds = [
            {
                "name": "BLS",
                "url": os.getenv("BLS_CALENDAR_ICS_URL", "https://www.bls.gov/schedule/news_release/bls.ics"),
                "kind": "ics",
            },
            {
                "name": "BEA",
                "url": os.getenv("BEA_CALENDAR_URL", "https://www.bea.gov/news/schedule/full"),
                "kind": "html",
                "keywords": ("GDP", "PCE", "Personal Income", "International Trade", "Corporate Profits"),
            },
            {
                "name": "Census",
                "url": os.getenv("CENSUS_CALENDAR_URL", "https://www.census.gov/economic-indicators/calendar-listview.html"),
                "kind": "census",
            },
            {
                "name": "NY Fed",
                "url": os.getenv("NYFED_CALENDAR_URL", "https://www.newyorkfed.org/research/national_economy/nationalecon_cal.html"),
                "kind": "html",
                "keywords": ("Empire State", "Consumer Expectations", "Manufacturing", "Inflation", "Treasury"),
            },
            {
                "name": "Federal Reserve",
                "url": os.getenv("FOMC_CALENDAR_URL", "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"),
                "kind": "fomc",
            },
        ]

        items: List[dict] = []
        sources: List[dict] = []
        for feed in feeds:
            feed_items, source = self._fetch_macro_feed(feed, start, end)
            items.extend(feed_items)
            sources.append(source)

        items = self._dedupe_events(items, ("date", "time", "title", "source"))[:32]
        result = {"items": items, "sources": sources}
        self._cache_set(cache_key, result)
        return result

    def _fetch_macro_feed(self, feed: dict, start: date, end: date) -> tuple[List[dict], dict]:
        name = feed["name"]
        url = feed["url"]
        source = {"name": name, "url": url, "configured": bool(url), "ok": False}
        if not url:
            source["reason"] = "missing_url"
            return [], source

        try:
            response = requests.get(url, timeout=self.timeout, headers={"User-Agent": "TradingBullDesk/1.0"})
            if response.status_code >= 400:
                source["reason"] = f"http_{response.status_code}"
                return [], source
        except requests.RequestException as exc:
            source["reason"] = str(exc)
            return [], source

        text = response.text
        if feed["kind"] == "ics":
            items = self._parse_ics(text, name, url, start, end)
        elif feed["kind"] == "fomc":
            items = self._parse_fomc(text, url, start, end)
        elif feed["kind"] == "census":
            items = self._parse_census(text, url, start, end)
        else:
            items = self._parse_release_html(text, name, url, start, end, feed.get("keywords", ()))

        source["ok"] = True
        source["count"] = len(items)
        return items, source

    def _parse_alpha_earnings(self, requested_symbol: str, text: str, start: date, end: date) -> List[dict]:
        stripped = text.strip()
        if not stripped:
            return []
        if stripped.startswith("{"):
            try:
                payload = json.loads(stripped)
            except ValueError:
                return []
            message = payload.get("Note") or payload.get("Information") or payload.get("Error Message")
            if message:
                return []

        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames or "reportDate" not in reader.fieldnames:
            return []

        items: List[dict] = []
        for row in reader:
            report_date = self._parse_date(row.get("reportDate"), start.year)
            if not report_date or report_date < start or report_date > end:
                continue
            symbol = (row.get("symbol") or requested_symbol).upper()
            items.append(
                {
                    "date": report_date.isoformat(),
                    "symbol": symbol,
                    "title": f"{symbol} earnings",
                    "name": row.get("name") or symbol,
                    "fiscal_date_ending": row.get("fiscalDateEnding") or "",
                    "estimate": row.get("estimate") or "",
                    "currency": row.get("currency") or "USD",
                    "source": "Alpha Vantage",
                }
            )
        items.sort(key=lambda item: (item["date"], item["symbol"]))
        return items

    def _parse_ics(self, text: str, source_name: str, url: str, start: date, end: date) -> List[dict]:
        lines = self._unfold_ics(text)
        events: List[dict] = []
        current: Dict[str, str] = {}
        in_event = False
        for line in lines:
            if line == "BEGIN:VEVENT":
                current = {}
                in_event = True
                continue
            if line == "END:VEVENT":
                in_event = False
                event = self._ics_event(current, source_name, url, start, end)
                if event:
                    events.append(event)
                current = {}
                continue
            if in_event and ":" in line:
                key, value = line.split(":", 1)
                current[key.split(";", 1)[0].upper()] = value.strip()
        events.sort(key=lambda item: (item["date"], item.get("time", ""), item["title"]))
        return events

    def _parse_fomc(self, html: str, url: str, start: date, end: date) -> List[dict]:
        text = self._html_text(html)
        events: List[dict] = []
        years = {start.year, end.year}
        for year in years:
            year_match = re.search(rf"{year}\s+FOMC Meetings(?P<body>.*?)(?:20\d{{2}}\s+FOMC Meetings|$)", text, re.IGNORECASE | re.DOTALL)
            body = year_match.group("body") if year_match else text
            for match in DATE_WORD_RE.finditer(body):
                event_date = self._date_from_match(match, year)
                if not event_date or event_date < start or event_date > end:
                    continue
                events.append(
                    {
                        "date": event_date.isoformat(),
                        "time": "2:00 PM",
                        "title": "FOMC policy decision",
                        "source": "Federal Reserve",
                        "category": "monetary_policy",
                        "importance": "high",
                        "url": url,
                    }
                )
        return self._dedupe_events(events, ("date", "title", "source"))

    def _parse_census(self, html: str, url: str, start: date, end: date) -> List[dict]:
        lines = self._html_lines(html)
        events: List[dict] = []
        for index, line in enumerate(lines):
            if line.lower() not in {"next", "next release"}:
                continue
            date_line = lines[index + 1] if index + 1 < len(lines) else ""
            event_date = self._parse_date(date_line, start.year)
            if not event_date or event_date < start or event_date > end:
                continue
            title = self._nearest_title(lines, index)
            events.append(
                {
                    "date": event_date.isoformat(),
                    "time": "8:30 AM",
                    "title": title,
                    "source": "U.S. Census Bureau",
                    "category": self._category(title),
                    "importance": self._importance(title),
                    "url": url,
                }
            )
        return self._dedupe_events(events, ("date", "title", "source"))

    def _parse_release_html(
        self,
        html: str,
        source_name: str,
        url: str,
        start: date,
        end: date,
        keywords: Iterable[str],
    ) -> List[dict]:
        text = self._html_text(html)
        compressed = re.sub(r"\s+", " ", text)
        events: List[dict] = []
        for match in DATE_WORD_RE.finditer(compressed):
            prefix = compressed[max(0, match.start() - 8) : match.start()].lower()
            if "view" in prefix:
                continue
            event_date = self._date_from_match(match, start.year)
            if not event_date or event_date < start or event_date > end:
                continue
            window = compressed[match.end() : match.end() + 220].strip()
            if keywords and not any(keyword.lower() in window.lower() for keyword in keywords):
                continue
            title = self._release_title_from_window(window)
            if not title:
                continue
            time_match = TIME_RE.search(window[:32])
            events.append(
                {
                    "date": event_date.isoformat(),
                    "time": time_match.group("time").replace(".", "").upper() if time_match else "",
                    "title": title,
                    "source": source_name,
                    "category": self._category(title),
                    "importance": self._importance(title),
                    "url": url,
                }
            )
        return self._dedupe_events(events, ("date", "title", "source"))

    def _ics_event(self, current: dict, source_name: str, url: str, start: date, end: date) -> Optional[dict]:
        title = self._clean_title(current.get("SUMMARY", ""))
        event_date, event_time = self._parse_ics_date(current.get("DTSTART", ""))
        if not title or not event_date or event_date < start or event_date > end:
            return None
        return {
            "date": event_date.isoformat(),
            "time": event_time,
            "title": title,
            "source": source_name,
            "category": self._category(title),
            "importance": self._importance(title),
            "url": url,
        }

    def _equity_symbols(self) -> List[str]:
        symbols: List[str] = []
        for item in self.config.get("symbols", []):
            symbol = str(item.get("symbol", "")).strip().upper()
            asset_type = str(item.get("type", "equity")).lower()
            if not symbol or asset_type not in {"equity", "stock", "stocks"}:
                continue
            if any(char in symbol for char in (":", "/", "-", ".")):
                continue
            symbols.append(symbol)
        return sorted(set(symbols))[:12]

    def _broker_configured(self) -> bool:
        checker = getattr(self.broker, "is_configured", None)
        return bool(checker and checker())

    def _month_end(self, start: date) -> date:
        if start.month == 12:
            return date(start.year + 1, 1, 1) - timedelta(days=1)
        return date(start.year, start.month + 1, 1) - timedelta(days=1)

    def _session_label(self, item: dict) -> str:
        open_time = str(item.get("open", "")).strip()
        close_time = str(item.get("close", "")).strip()
        if open_time and close_time:
            return f"{open_time}-{close_time} ET"
        return "Regular market session"

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _parse_date(self, value: Any, default_year: int) -> Optional[date]:
        text = str(value or "").strip()
        if not text:
            return None
        iso_match = ISO_DATE_RE.search(text)
        if iso_match:
            return self._safe_date(int(iso_match.group("year")), int(iso_match.group("month")), int(iso_match.group("day")))
        us_match = US_DATE_RE.search(text)
        if us_match:
            return self._safe_date(int(us_match.group("year")), int(us_match.group("month")), int(us_match.group("day")))
        word_match = DATE_WORD_RE.search(text)
        if word_match:
            return self._date_from_match(word_match, default_year)
        return None

    def _date_from_match(self, match: re.Match[str], default_year: int) -> Optional[date]:
        month = MONTHS.get(match.group("month").lower())
        day_text = match.group("end_day") or match.group("day")
        year = int(match.group("year") or default_year)
        if not month or not day_text:
            return None
        return self._safe_date(year, month, int(day_text))

    def _safe_date(self, year: int, month: int, day: int) -> Optional[date]:
        try:
            return date(year, month, day)
        except ValueError:
            return None

    def _parse_ics_date(self, value: str) -> tuple[Optional[date], str]:
        text = value.strip()
        if not text:
            return None, ""
        date_text = text[:8]
        try:
            parsed_date = date(int(date_text[:4]), int(date_text[4:6]), int(date_text[6:8]))
        except ValueError:
            return None, ""
        if "T" not in text:
            return parsed_date, ""
        time_part = text.split("T", 1)[1][:4]
        try:
            hour = int(time_part[:2])
            minute = int(time_part[2:4])
        except ValueError:
            return parsed_date, ""
        suffix = "AM" if hour < 12 else "PM"
        hour_12 = hour % 12 or 12
        return parsed_date, f"{hour_12}:{minute:02d} {suffix}"

    def _unfold_ics(self, text: str) -> List[str]:
        lines: List[str] = []
        for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            if raw.startswith((" ", "\t")) and lines:
                lines[-1] += raw[1:]
            else:
                lines.append(raw.strip())
        return lines

    def _html_text(self, html: str) -> str:
        text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
        text = re.sub(r"(?i)<br\s*/?>|</p>|</tr>|</div>|</li>|</h\d>", "\n", text)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        return unescape(re.sub(r"[ \t]+", " ", text))

    def _html_lines(self, html: str) -> List[str]:
        return [line.strip() for line in self._html_text(html).splitlines() if line.strip()]

    def _release_title_from_window(self, text: str) -> str:
        cleaned = unescape(text or "")
        cleaned = re.sub(r"\bN\s+ews\b", "News", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bD\s+ata\b", "Data", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -|")
        cleaned = TIME_RE.sub("", cleaned, count=1).strip(" -|")
        cleaned = re.sub(r"^(News|Data|Release|View)\s+", "", cleaned, flags=re.IGNORECASE).strip(" -|")
        boundary = re.search(
            rf"\s+(?:View\s+)?(?:{MONTH_PATTERN})\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+20\d{{2}})?\s+\d{{1,2}}:\d{{2}}\s*(?:AM|PM)",
            cleaned,
            flags=re.IGNORECASE,
        )
        if boundary:
            cleaned = cleaned[: boundary.start()]
        return self._clean_title(cleaned)

    def _nearest_title(self, lines: List[str], index: int) -> str:
        ignored = {
            "released",
            "latest",
            "next",
            "next release",
            "current",
            "prior",
            "difference",
            "chart",
            "actions",
            "view",
            "pin",
            "info",
        }
        for line in reversed(lines[max(0, index - 18) : index]):
            cleaned = self._clean_title(line)
            if not cleaned or cleaned.lower() in ignored:
                continue
            if self._parse_date(cleaned, datetime.now().year):
                continue
            if len(cleaned) >= 5:
                return cleaned
        return "Census economic indicator"

    def _clean_title(self, text: str) -> str:
        cleaned = unescape(text or "")
        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = re.sub(r"^(News|Data|Release|View)\s+", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip(" -|")
        if TIME_RE.match(cleaned):
            cleaned = TIME_RE.sub("", cleaned, count=1).strip(" -|")
        return cleaned[:140]

    def _category(self, title: str) -> str:
        text = title.lower()
        if "fomc" in text or "federal reserve" in text:
            return "monetary_policy"
        if any(term in text for term in ("cpi", "ppi", "inflation", "pce")):
            return "inflation"
        if any(term in text for term in ("employment", "payroll", "unemployment", "jobs")):
            return "labor"
        if "gdp" in text or "personal income" in text:
            return "growth"
        if any(term in text for term in ("retail", "housing", "durable", "manufacturing", "consumer")):
            return "macro"
        return "macro"

    def _importance(self, title: str) -> str:
        text = title.lower()
        high_terms = ("fomc", "cpi", "ppi", "payroll", "employment", "unemployment", "gdp", "pce")
        medium_terms = ("retail", "housing", "durable", "manufacturing", "consumer", "personal income")
        if any(term in text for term in high_terms):
            return "high"
        if any(term in text for term in medium_terms):
            return "medium"
        return "normal"

    def _dedupe_events(self, items: List[dict], keys: Iterable[str]) -> List[dict]:
        seen = set()
        output: List[dict] = []
        for item in sorted(items, key=lambda value: (value.get("date", ""), value.get("time", ""), value.get("title", ""))):
            identity = tuple(item.get(key, "") for key in keys)
            if identity in seen:
                continue
            seen.add(identity)
            output.append(item)
        return output

    def _cache_get(self, key: str) -> Any:
        cached = self._cache.get(key)
        if not cached:
            return None
        created_at, value = cached
        if time.time() - created_at > self.cache_seconds:
            self._cache.pop(key, None)
            return None
        return value

    def _cache_set(self, key: str, value: Any) -> None:
        self._cache[key] = (time.time(), value)
