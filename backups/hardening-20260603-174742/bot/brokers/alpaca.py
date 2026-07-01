from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from ..core.types import Fill, Order, OrderType, Position


@dataclass(frozen=True)
class AlpacaPaperConfig:
    key_id: str
    secret_key: str
    base_url: str = "https://paper-api.alpaca.markets"
    data_url: str = "https://data.alpaca.markets"
    timeout_seconds: int = 20

    @classmethod
    def from_env(cls) -> "AlpacaPaperConfig":
        return cls(
            key_id=os.getenv("APCA_API_KEY_ID", ""),
            secret_key=os.getenv("APCA_API_SECRET_KEY", ""),
            base_url=os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets"),
            data_url=os.getenv("APCA_API_DATA_URL", "https://data.alpaca.markets"),
        )


class AlpacaPaperBroker:
    """Small REST adapter for Alpaca paper trading.

    The bot uses raw REST calls instead of an SDK so the paper-trading path stays
    transparent and easy to audit.
    """

    def __init__(self, config: Optional[AlpacaPaperConfig] = None) -> None:
        self.config = config or AlpacaPaperConfig.from_env()

    def is_configured(self) -> bool:
        return bool(self.config.key_id and self.config.secret_key)

    def _headers(self) -> dict:
        return {
            "APCA-API-KEY-ID": self.config.key_id,
            "APCA-API-SECRET-KEY": self.config.secret_key,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs) -> Any:
        if not self.is_configured():
            raise RuntimeError("Alpaca paper credentials are missing.")
        url = f"{self.config.base_url.rstrip('/')}{path}"
        response = requests.request(
            method,
            url,
            headers=self._headers(),
            timeout=self.config.timeout_seconds,
            **kwargs,
        )
        if response.status_code >= 300:
            raise RuntimeError(f"Alpaca {method} {path} failed: {response.status_code} {response.text}")
        if not response.text:
            return {}
        return response.json()

    def validate_connection(self) -> dict:
        if not self.is_configured():
            return {"ok": False, "reason": "missing_credentials"}
        try:
            account = self.get_account()
        except Exception as exc:
            return {"ok": False, "reason": str(exc)}
        return {
            "ok": True,
            "account_status": account.get("status"),
            "trading_blocked": account.get("trading_blocked"),
            "account_number_tail": str(account.get("account_number", ""))[-4:],
            "paper": self.config.base_url.startswith("https://paper-api."),
        }

    def get_account(self) -> dict:
        return self._request("GET", "/v2/account")

    def get_positions_raw(self) -> List[dict]:
        data = self._request("GET", "/v2/positions")
        return data if isinstance(data, list) else []

    def get_orders_raw(
        self,
        *,
        status: str = "open",
        limit: int = 100,
        direction: str = "desc",
        nested: bool = True,
        symbols: Optional[str] = None,
    ) -> List[dict]:
        params: Dict[str, Any] = {
            "status": status,
            "limit": limit,
            "direction": direction,
            "nested": "true" if nested else "false",
        }
        if symbols:
            params["symbols"] = symbols
        data = self._request("GET", "/v2/orders", params=params)
        return data if isinstance(data, list) else []

    def get_portfolio_history_raw(self, *, period: str = "1M", timeframe: str = "1D") -> dict:
        data = self._request(
            "GET",
            "/v2/account/portfolio/history",
            params={"period": period, "timeframe": timeframe},
        )
        return data if isinstance(data, dict) else {}

    def get_activities_raw(
        self,
        *,
        activity_types: str = "FILL",
        after: Optional[str] = None,
        until: Optional[str] = None,
        direction: str = "desc",
        page_size: int = 100,
    ) -> List[dict]:
        params: Dict[str, Any] = {
            "activity_types": activity_types,
            "direction": direction,
            "page_size": page_size,
        }
        if after:
            params["after"] = after
        if until:
            params["until"] = until
        data = self._request("GET", "/v2/account/activities", params=params)
        return data if isinstance(data, list) else []

    def get_calendar_raw(self, *, start: Optional[str] = None, end: Optional[str] = None) -> List[dict]:
        params: Dict[str, Any] = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        data = self._request("GET", "/v2/calendar", params=params)
        return data if isinstance(data, list) else []

    def get_positions(self) -> List[Position]:
        positions: List[Position] = []
        for item in self.get_positions_raw():
            qty = int(float(item.get("qty", 0)))
            if item.get("side") == "short":
                qty = -abs(qty)
            positions.append(
                Position(
                    symbol=item.get("symbol", ""),
                    qty=qty,
                    entry_price=float(item.get("avg_entry_price", 0.0)),
                    entry_time=datetime.utcnow(),
                    stop_price=0.0,
                    initial_stop=0.0,
                    risk_per_share=0.0,
                )
            )
        return positions

    def submit_order(self, order: Order) -> Fill:
        payload = self.order_payload_from_order(order)
        response = self.submit_order_payload(payload)
        price = self._response_fill_price(response, order)
        return Fill(order=order, price=price, timestamp=datetime.utcnow(), slippage=0.0, commission=0.0)

    def submit_order_payload(self, payload: dict) -> dict:
        return self._request("POST", "/v2/orders", json=payload)

    def cancel_all_orders(self) -> dict:
        return self._request("DELETE", "/v2/orders")

    def close(self) -> None:
        return None

    def order_payload_from_order(
        self,
        order: Order,
        *,
        time_in_force: str = "day",
        attach_stop_loss: bool = True,
        take_profit_price: Optional[float] = None,
    ) -> dict:
        payload: Dict[str, Any] = {
            "symbol": order.symbol,
            "qty": str(order.qty),
            "side": order.side.value,
            "type": order.order_type.value,
            "time_in_force": time_in_force,
            "client_order_id": order.metadata.get("client_order_id", f"velez-{uuid.uuid4().hex[:24]}"),
        }
        if order.order_type == OrderType.LIMIT:
            if order.limit_price is None:
                raise ValueError("limit_price is required for limit orders")
            payload["limit_price"] = self._price(order.limit_price)

        stop_price = order.metadata.get("stop_price")
        if attach_stop_loss and stop_price:
            if take_profit_price is not None:
                payload["order_class"] = "bracket"
                payload["take_profit"] = {"limit_price": self._price(take_profit_price)}
            else:
                payload["order_class"] = "oto"
            payload["stop_loss"] = {"stop_price": self._price(float(stop_price))}

        return payload

    def build_entry_payload(
        self,
        *,
        symbol: str,
        side: str,
        qty: int,
        order_type: str,
        entry_price: Optional[float],
        stop_price: float,
        client_order_id: Optional[str] = None,
        time_in_force: str = "day",
        take_profit_price: Optional[float] = None,
    ) -> dict:
        if qty <= 0:
            raise ValueError("qty must be positive")
        payload: Dict[str, Any] = {
            "symbol": symbol,
            "qty": str(qty),
            "side": side,
            "type": order_type,
            "time_in_force": time_in_force,
            "client_order_id": client_order_id or f"velez-{uuid.uuid4().hex[:24]}",
            "order_class": "bracket" if take_profit_price is not None else "oto",
            "stop_loss": {"stop_price": self._price(stop_price)},
        }
        if order_type == "limit":
            if entry_price is None:
                raise ValueError("entry_price is required for limit orders")
            payload["limit_price"] = self._price(entry_price)
        if take_profit_price is not None:
            payload["take_profit"] = {"limit_price": self._price(take_profit_price)}
        return payload

    def _response_fill_price(self, response: dict, order: Order) -> float:
        filled_avg = response.get("filled_avg_price")
        if filled_avg:
            return float(filled_avg)
        if order.limit_price is not None:
            return float(order.limit_price)
        return float(order.metadata.get("entry_price", 0.0))

    def _price(self, price: float) -> str:
        return f"{float(price):.2f}"
