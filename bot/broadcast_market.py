from __future__ import annotations

import math
import os
import threading
import time
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urlparse

import requests


BROADCAST_SYMBOLS = ("SPY", "QQQ", "VIX", "DXY", "GLD", "EUR/USD", "BTC", "ETH")
SYMBOL_ALIASES = {
    "BTC/USD": "BTC",
    "BTCUSD": "BTC",
    "BTC-USD": "BTC",
    "ETH/USD": "ETH",
    "ETHUSD": "ETH",
    "ETH-USD": "ETH",
    "EUR_USD": "EUR/USD",
    "EURUSD": "EUR/USD",
    "^VIX": "VIX",
}


class BroadcastMarketService:
    """Read-only, short-lived market display feed for Bull Pilot Broadcast.

    This service is intentionally isolated from execution. It can read from an
    approved shared endpoint, Tradier, and an independent Alpaca display feed. It never submits, modifies, or cancels
    orders and never invents a price when providers are unavailable.
    """

    def __init__(self, broker: Any, *, session: Any = requests) -> None:
        self.broker = broker
        self.tradier_token = os.getenv("DESK_DISPLAY_TRADIER_TOKEN", os.getenv("TRADIER_ACCESS_TOKEN", "")).strip()
        self.tradier_sandbox = os.getenv("DESK_DISPLAY_TRADIER_ENV", "production") == "sandbox"
        self.tradier_base = "https://sandbox.tradier.com/v1" if self.tradier_sandbox else "https://api.tradier.com/v1"
        self.alpaca_key = os.getenv("DESK_DISPLAY_ALPACA_KEY", os.getenv("APCA_API_KEY_ID", "")).strip()
        self.alpaca_secret = os.getenv("DESK_DISPLAY_ALPACA_SECRET", os.getenv("APCA_API_SECRET_KEY", "")).strip()
        self.alpaca_feed = os.getenv("DESK_DISPLAY_ALPACA_FEED", "iex").strip().lower()
        if self.alpaca_feed not in {"iex", "sip", "delayed_sip"}:
            self.alpaca_feed = "iex"
        self.market_session = "unknown"
        self.session = session
        self.cache_seconds = self._bounded_int(os.getenv("BULLPILOT_BROADCAST_CACHE_SECONDS", "30"), 10, 300, 30)
        self.timeout_seconds = self._bounded_int(os.getenv("BULLPILOT_BROADCAST_TIMEOUT_SECONDS", "8"), 2, 30, 8)
        self.feed_url = os.getenv("DENDRIX_BROADCAST_FEED_URL", "").strip()
        self.feed_token = os.getenv("DENDRIX_BROADCAST_FEED_TOKEN", "").strip()
        self._lock = threading.Lock()
        self._cached_at = 0.0
        self._cached_payload: Optional[dict] = None

    def payload(self, *, refresh: bool = False) -> dict:
        now = time.monotonic()
        with self._lock:
            if not refresh and self._cached_payload and now - self._cached_at < self.cache_seconds:
                return deepcopy(self._cached_payload)

            payload = self._fresh_payload()
            self._cached_at = time.monotonic()
            self._cached_payload = deepcopy(payload)
            return payload

    def _fresh_payload(self) -> dict:
        attempts, providers, found = [], [], {}
        self.market_session = "unknown"
        feeds = []
        if self.feed_url:
            feeds.append(("dendrix", self._dendrix_payload))
        if self.tradier_token:
            feeds.append(("tradier", self._tradier_payload))
        if self._alpaca_headers():
            feeds.append(("alpaca", self._alpaca_payload))
        for name, load in feeds:
            try:
                value = load()
                added = False
                for item in value["items"]:
                    symbol = item["symbol"]
                    if item.get("status") != "available" or symbol not in BROADCAST_SYMBOLS:
                        continue
                    previous = found.get(symbol)
                    threshold = 7 * 86400 if self.market_session == "closed" and symbol not in {"BTC", "ETH"} else 1200 if item.get("delayed") else 300
                    old_stamp = self._timestamp_seconds(previous.get("as_of")) if previous else None
                    new_stamp = self._timestamp_seconds(item.get("as_of"))
                    if previous is None or ((old_stamp is None or time.time() - old_stamp > threshold) and new_stamp and time.time() - new_stamp <= threshold):
                        found[symbol] = {**item, "source": item.get("source") or value["source"], "fallback": name == "alpaca" and symbol not in {"BTC", "ETH"} and bool(self.tradier_token), "replaced_stale_primary": bool(previous)}
                        added = True
                if added:
                    providers.append(value["source"])
                else:
                    attempts.append(name + "_feed_empty")
            except Exception as exc:
                attempts.append(name + ":" + type(exc).__name__)
        prior = {r["symbol"]: r for r in (self._cached_payload or {}).get("items", [])}
        rows = []
        for symbol in BROADCAST_SYMBOLS:
            row = found.get(symbol)
            if row is None and prior.get(symbol, {}).get("price") is not None:
                row = {**prior[symbol], "status": "stale", "stale": True, "freshness": "refresh_failed"}
            row = row or self._unavailable_item(symbol)
            row["instrument_label"] = "SPDR Gold Shares ETF" if symbol == "GLD" else symbol
            row["market_status"] = "continuous" if symbol in {"BTC", "ETH"} else self.market_session
            if row.get("status") == "available":
                stamp = self._timestamp_seconds(row.get("as_of"))
                age = max(0, time.time() - stamp) if stamp else None
                threshold = 7 * 86400 if row["market_status"] == "closed" else 1200 if row.get("delayed") else 300
                row["stale"] = age is None or age > threshold
                row["freshness"] = "unknown_time" if age is None else "stale_quote" if row["stale"] else "market_closed" if row["market_status"] == "closed" else "delayed" if row.get("delayed") else "current"
                if row["stale"]:
                    row["status"] = "stale"
            rows.append(row)
        available = any(r.get("price") is not None for r in rows)
        return {"ok": available, "source": " / ".join(providers) or ("Last available quotes" if available else "No approved provider"),
                "items": rows, "as_of": self._latest_as_of(rows), "display_only": True,
                "delayed": any(r.get("delayed") for r in rows if r.get("price") is not None),
                "stale": any(r.get("stale") for r in rows if r.get("price") is not None),
                "market_status": self.market_session, "providers_checked": attempts,
                "reason": "ready" if available else "market_feed_unavailable",
                "coverage_note": "Tradier production uses consolidated equities; Alpaca " + self.alpaca_feed.upper() + " coverage is labeled per quote. GLD is an ETF."}

    @staticmethod
    def _timestamp_seconds(value):
        try:
            if isinstance(value, (int, float)):
                return value / 1000 if value > 100000000000 else value
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
        except (ValueError, TypeError, OverflowError, OSError):
            return None

    def _alpaca_headers(self):
        if self.alpaca_key and self.alpaca_secret:
            return {"APCA-API-KEY-ID": self.alpaca_key, "APCA-API-SECRET-KEY": self.alpaca_secret}
        # Preserve older Alpaca deployments while dedicated display credentials roll out.
        if getattr(getattr(self.broker, "config", None), "data_url", None) and callable(getattr(self.broker, "_headers", None)) and getattr(self.broker, "is_configured", lambda: False)():
            return self.broker._headers()
        return {}

    def _tradier_payload(self):
        headers = {"Authorization": "Bearer " + self.tradier_token, "Accept": "application/json"}
        response = self.session.get(self.tradier_base + "/markets/quotes", headers=headers,
                                    params={"symbols": "SPY,QQQ,VIX,DXY,GLD"}, timeout=self.timeout_seconds)
        response.raise_for_status()
        raw = response.json().get("quotes") or {}
        quotes = raw.get("quote") or []
        if isinstance(quotes, dict):
            quotes = [quotes]
        try:
            clock = self.session.get(self.tradier_base + "/markets/clock", headers=headers, timeout=self.timeout_seconds)
            clock.raise_for_status()
            state = (clock.json().get("clock") or {}).get("state")
            self.market_session = state if state in {"open", "closed", "premarket", "postmarket"} else "unknown"
        except Exception:
            self.market_session = "unknown"
        source = "Tradier delayed" if self.tradier_sandbox else "Tradier consolidated"
        rows = []
        for q in quotes:
            symbol = str(q.get("symbol", "")).upper()
            price = self._number(q.get("last"))
            if symbol not in BROADCAST_SYMBOLS or price is None or price <= 0:
                continue
            timestamp = self._timestamp_seconds(q.get("trade_date"))
            rows.append({"symbol": symbol, "price": price, "change_percent": self._number(q.get("change_percentage")),
                         "source": source, "delayed": self.tradier_sandbox, "status": "available",
                         "as_of": datetime.fromtimestamp(timestamp, timezone.utc).isoformat() if timestamp else None})
        return {"items": rows, "source": source}

    def _dendrix_payload(self) -> dict:
        self._validate_configured_url(self.feed_url)
        headers = {"Accept": "application/json"}
        if self.feed_token:
            headers["Authorization"] = f"Bearer {self.feed_token}"
        response = self.session.get(self.feed_url, headers=headers, timeout=self.timeout_seconds)
        response.raise_for_status()
        raw = response.json()
        items = self._normalize_external_items(raw.get("items") if isinstance(raw, dict) else [])
        if isinstance(raw, dict) and raw.get("delayed"):
            for item in items:
                item["delayed"] = True
        return {
            "ok": any(item["status"] == "available" for item in items),
            "source": str(raw.get("source") or "Dendrix shared feed")[:80] if isinstance(raw, dict) else "Dendrix shared feed",
            "delayed": bool(raw.get("delayed", False)) if isinstance(raw, dict) else False,
            "as_of": self._safe_timestamp(raw.get("as_of")) if isinstance(raw, dict) else self._now(),
            "items": items,
            "display_only": True,
        }

    def _alpaca_payload(self) -> dict:
        headers = self._alpaca_headers()
        by_symbol = {}
        requests_to_make = [
            ("https://data.alpaca.markets/v2/stocks/snapshots", {"symbols": "SPY,QQQ,GLD", "feed": self.alpaca_feed}, "Alpaca " + self.alpaca_feed.upper()),
            ("https://data.alpaca.markets/v1beta3/crypto/us/snapshots", {"symbols": "BTC/USD,ETH/USD"}, "Alpaca crypto"),
        ]
        for url, params, source in requests_to_make:
            try:
                response = self.session.get(url, headers=headers, params=params, timeout=self.timeout_seconds)
                response.raise_for_status()
                for symbol, snapshot in self._snapshot_mapping(response.json()).items():
                    item = self._snapshot_item(symbol, snapshot, delayed=params.get("feed") == "delayed_sip")
                    if item:
                        item["source"] = source
                        by_symbol[item["symbol"]] = item
            except Exception:
                continue
        return {"items": list(by_symbol.values()), "source": "Alpaca " + self.alpaca_feed.upper() + " + crypto"}

    def _snapshot_mapping(self, payload: Any) -> dict:
        if not isinstance(payload, dict):
            return {}
        snapshots = payload.get("snapshots")
        return snapshots if isinstance(snapshots, dict) else payload

    def _snapshot_item(self, symbol: str, snapshot: Any, *, delayed: bool) -> Optional[dict]:
        if not isinstance(snapshot, dict):
            return None
        latest = snapshot.get("latestTrade") or snapshot.get("latest_trade") or {}
        daily = snapshot.get("dailyBar") or snapshot.get("daily_bar") or {}
        previous = snapshot.get("prevDailyBar") or snapshot.get("prev_daily_bar") or {}
        price = self._number(latest.get("p") or latest.get("price") or daily.get("c") or daily.get("close"))
        previous_close = self._number(previous.get("c") or previous.get("close"))
        if price is None or price <= 0:
            return None
        change_percent = None
        if previous_close not in (None, 0):
            change_percent = round((price - previous_close) / previous_close * 100, 4)
        as_of = latest.get("t") or latest.get("timestamp") or daily.get("t") or daily.get("timestamp")
        return {
            "symbol": self._normalize_symbol(symbol),
            "price": round(price, 6),
            "change_percent": change_percent,
            "status": "available",
            "delayed": delayed,
            "as_of": self._safe_timestamp(as_of),
        }

    def _normalize_external_items(self, rows: Any) -> list[dict]:
        found: Dict[str, dict] = {}
        if isinstance(rows, Iterable) and not isinstance(rows, (str, bytes, dict)):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                symbol = self._normalize_symbol(row.get("symbol"))
                if symbol not in BROADCAST_SYMBOLS:
                    continue
                price = self._number(row.get("price"))
                change_percent = self._number(row.get("change_percent"))
                if price is None:
                    found[symbol] = self._unavailable_item(symbol)
                    continue
                found[symbol] = {
                    "symbol": symbol,
                    "price": round(price, 6),
                    "change_percent": round(change_percent, 4) if change_percent is not None else None,
                    "status": "available",
                    "delayed": bool(row.get("delayed", False)),
                    "as_of": self._safe_timestamp(row.get("as_of")),
                }
        return [found.get(symbol, self._unavailable_item(symbol)) for symbol in BROADCAST_SYMBOLS]

    def _unavailable_payload(self, attempts: list[str]) -> dict:
        return {
            "ok": False,
            "source": "No approved provider",
            "delayed": True,
            "as_of": self._now(),
            "items": [self._unavailable_item(symbol) for symbol in BROADCAST_SYMBOLS],
            "reason": "market_feed_unavailable",
            "providers_checked": attempts,
            "display_only": True,
        }

    def _unavailable_item(self, symbol: str) -> dict:
        return {
            "symbol": symbol,
            "price": None,
            "change_percent": None,
            "status": "unavailable",
            "delayed": True,
            "as_of": None,
            "stale": False,
            "freshness": "unavailable",
            "source": None,
        }

    def _normalize_symbol(self, value: Any) -> str:
        symbol = str(value or "").strip().upper()
        return SYMBOL_ALIASES.get(symbol, symbol)

    def _latest_as_of(self, rows: list[dict]) -> str:
        timestamps = [str(row.get("as_of")) for row in rows if row.get("as_of")]
        return max(timestamps) if timestamps else self._now()

    def _safe_timestamp(self, value: Any) -> Optional[str]:
        if value in (None, ""):
            return None
        text = str(value).strip()
        return text[:64]

    def _validate_configured_url(self, value: str) -> None:
        parsed = urlparse(value)
        host = str(parsed.hostname or "").lower()
        if parsed.scheme == "https" and host:
            return
        if parsed.scheme == "http" and host in {"127.0.0.1", "localhost", "::1"}:
            return
        raise ValueError("DENDRIX_BROADCAST_FEED_URL must use HTTPS or local HTTP")

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        try:
            number = float(value) if value not in (None, "") else None
            return number if number is not None and math.isfinite(number) else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _bounded_int(value: Any, minimum: int, maximum: int, fallback: int) -> int:
        try:
            return max(minimum, min(maximum, int(value)))
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
