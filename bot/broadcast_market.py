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


BROADCAST_SYMBOLS = ("SPY", "QQQ", "VIX", "DXY", "GOLD", "EUR/USD", "BTC", "ETH")
SYMBOL_ALIASES = {
    "BTC/USD": "BTC",
    "BTCUSD": "BTC",
    "BTC-USD": "BTC",
    "ETH/USD": "ETH",
    "ETHUSD": "ETH",
    "ETH-USD": "ETH",
    "EUR_USD": "EUR/USD",
    "EURUSD": "EUR/USD",
    "XAU/USD": "GOLD",
    "XAU_USD": "GOLD",
    "GLD": "GOLD",
    "^VIX": "VIX",
}


class BroadcastMarketService:
    """Read-only, short-lived market display feed for Bull Pilot Broadcast.

    This service is intentionally isolated from execution. It can read from an
    approved Dendrix/shared endpoint, then use existing Alpaca market-data
    credentials as a limited fallback. It never submits, modifies, or cancels
    orders and never invents a price when providers are unavailable.
    """

    def __init__(self, broker: Any, *, session: Any = requests) -> None:
        self.broker = broker
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
        with self._lock:
            self._cached_at = now
            self._cached_payload = deepcopy(payload)
        return payload

    def _fresh_payload(self) -> dict:
        attempts = []
        if self.feed_url:
            try:
                payload = self._dendrix_payload()
                if any(item.get("status") == "available" for item in payload["items"]):
                    return payload
                attempts.append("dendrix_feed_empty")
            except Exception as exc:  # fail closed to the next read-only source
                attempts.append(f"dendrix:{type(exc).__name__}")

        if callable(getattr(self.broker, "is_configured", None)) and self.broker.is_configured() and getattr(getattr(self.broker, "config", None), "data_url", None) and callable(getattr(self.broker, "_headers", None)):
            try:
                payload = self._alpaca_payload()
                if any(item.get("status") == "available" for item in payload["items"]):
                    payload["fallback"] = bool(attempts)
                    return payload
                attempts.append("alpaca_feed_empty")
            except Exception as exc:
                attempts.append(f"alpaca:{type(exc).__name__}")

        return self._unavailable_payload(attempts)

    def _dendrix_payload(self) -> dict:
        self._validate_configured_url(self.feed_url)
        headers = {"Accept": "application/json"}
        if self.feed_token:
            headers["Authorization"] = f"Bearer {self.feed_token}"
        response = self.session.get(self.feed_url, headers=headers, timeout=self.timeout_seconds)
        response.raise_for_status()
        raw = response.json()
        items = self._normalize_external_items(raw.get("items") if isinstance(raw, dict) else [])
        return {
            "ok": any(item["status"] == "available" for item in items),
            "source": str(raw.get("source") or "Dendrix shared feed")[:80] if isinstance(raw, dict) else "Dendrix shared feed",
            "delayed": bool(raw.get("delayed", False)) if isinstance(raw, dict) else False,
            "as_of": self._safe_timestamp(raw.get("as_of")) if isinstance(raw, dict) else self._now(),
            "items": items,
            "display_only": True,
        }

    def _alpaca_payload(self) -> dict:
        base_url = str(self.broker.config.data_url).rstrip("/")
        headers = self.broker._headers()
        stock_response = self.session.get(
            f"{base_url}/v2/stocks/snapshots",
            headers=headers,
            params={"symbols": "SPY,QQQ", "feed": "iex"},
            timeout=self.timeout_seconds,
        )
        stock_response.raise_for_status()
        stock_payload = stock_response.json() if stock_response.text else {}

        crypto_payload: dict = {}
        try:
            crypto_response = self.session.get(
                f"{base_url}/v1beta3/crypto/us/snapshots",
                headers=headers,
                params={"symbols": "BTC/USD,ETH/USD"},
                timeout=self.timeout_seconds,
            )
            crypto_response.raise_for_status()
            crypto_payload = crypto_response.json() if crypto_response.text else {}
        except requests.RequestException:
            crypto_payload = {}

        by_symbol: Dict[str, dict] = {}
        for symbol, snapshot in self._snapshot_mapping(stock_payload).items():
            normalized = self._snapshot_item(symbol, snapshot, delayed=False)
            if normalized:
                by_symbol[normalized["symbol"]] = normalized
        for symbol, snapshot in self._snapshot_mapping(crypto_payload).items():
            normalized = self._snapshot_item(symbol, snapshot, delayed=False)
            if normalized:
                by_symbol[normalized["symbol"]] = normalized

        items = [by_symbol.get(symbol, self._unavailable_item(symbol)) for symbol in BROADCAST_SYMBOLS]
        return {
            "ok": any(item["status"] == "available" for item in items),
            "source": "Alpaca IEX + crypto",
            "delayed": False,
            "as_of": self._latest_as_of(items),
            "items": items,
            "coverage_note": "US equities use Alpaca's IEX feed; unavailable instruments remain explicitly unavailable.",
            "display_only": True,
        }

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
        if price is None:
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
