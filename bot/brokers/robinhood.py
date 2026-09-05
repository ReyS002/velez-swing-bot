"""Robinhood Agentic equities broker for the Velez Trading Bot.

The adapter speaks only to the loopback Hermes bridge. It previews every
order, defaults to shadow mode, and never retries an ambiguous placement.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, List, Mapping, Optional
from uuid import uuid4

import requests

from ..core.types import Bar, Fill, Order, Position


class RobinhoodBrokerError(RuntimeError):
    pass


def _enabled(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class RobinhoodAgenticConfig:
    bridge_url: str
    bridge_key: str
    account_number: str
    shadow_mode: bool
    execution_enabled: bool
    protective_stops_verified: bool
    timeout_seconds: float = 12.0
    base_url: str = "agentic://robinhood"
    execution_gateway_url: str = ""
    execution_gateway_token: str = ""

    @classmethod
    def from_env(cls) -> "RobinhoodAgenticConfig":
        return cls(
            bridge_url=os.getenv("HERMES_ROBINHOOD_BRIDGE_URL", "http://127.0.0.1:8188").rstrip("/"),
            bridge_key=os.getenv("HERMES_ROBINHOOD_BRIDGE_KEY", "").strip(),
            account_number=(
                os.getenv("ROBINHOOD_AGENTIC_ACCOUNT_NUMBER", "").strip()
                or os.getenv("ROBINHOOD_AGENTIC_ACCOUNT_ID", "").strip()
            ),
            shadow_mode=_enabled("VELEZ_ROBINHOOD_SHADOW_MODE", True),
            execution_enabled=_enabled("VELEZ_ROBINHOOD_EXECUTION_ENABLED", False),
            protective_stops_verified=_enabled("VELEZ_ROBINHOOD_PROTECTIVE_STOPS_VERIFIED", False),
            execution_gateway_url=os.getenv("BULLPILOT_EXECUTION_GATEWAY_URL", "").rstrip("/"),
            execution_gateway_token=os.getenv("BULLPILOT_EXECUTION_GATEWAY_TOKEN", "").strip(),
        )


class BullPilotExecutionGateway:
    """Authenticated client for Bull Pilot's immutable prepare/submit API.

    This deliberately has no Robinhood concepts.  Velez sends a
    broker-neutral order intent and never receives an approval artifact.
    """

    def __init__(self, *, url: str, token: str, timeout_seconds: float) -> None:
        self.url = url.rstrip("/")
        self.token = token
        self.timeout_seconds = timeout_seconds

    @property
    def ready(self) -> bool:
        return bool(self.url and self.token)

    def _request(self, path: str, body: Mapping[str, Any]) -> dict[str, Any]:
        if not self.ready:
            raise RobinhoodBrokerError("bullpilot_execution_gateway_not_configured")
        try:
            response = requests.post(
                f"{self.url}{path}",
                headers={
                    "X-Execution-Gateway-Token": self.token,
                    "X-Execution-Gateway-Request-Id": str(uuid4()),
                    "X-Execution-Gateway-Timestamp": datetime.now(timezone.utc).isoformat(),
                },
                json=dict(body), timeout=self.timeout_seconds,
            )
        except requests.Timeout as error:
            raise RobinhoodBrokerError("bullpilot_execution_gateway_timeout_unknown") from error
        except requests.RequestException as error:
            raise RobinhoodBrokerError(f"bullpilot_execution_gateway_unavailable:{type(error).__name__}") from error
        try:
            payload = response.json()
        except ValueError as error:
            raise RobinhoodBrokerError("bullpilot_execution_gateway_invalid_json") from error
        if response.status_code != 200 or not isinstance(payload, Mapping):
            raise RobinhoodBrokerError(f"bullpilot_execution_gateway_http_{response.status_code}")
        return dict(payload)

    def prepare(self, intent: Mapping[str, Any], *, purpose: str) -> dict[str, Any]:
        return self._request("/internal/execution/prepare", {"payload": dict(intent), "purpose": purpose})

    def submit(self, *, prepared_intent_id: str, intent_fingerprint: str, authorization_ref: str | None) -> dict[str, Any]:
        body: dict[str, Any] = {"prepared_intent_id": prepared_intent_id, "intent_fingerprint": intent_fingerprint}
        if authorization_ref:
            body["authorization_ref"] = authorization_ref
        return self._request("/internal/execution/submit", body)


class RobinhoodAgenticBroker:
    def __init__(self, config: Optional[RobinhoodAgenticConfig] = None) -> None:
        self.config = config or RobinhoodAgenticConfig.from_env()
        self.execution_gateway = BullPilotExecutionGateway(
            url=self.config.execution_gateway_url,
            token=self.config.execution_gateway_token,
            timeout_seconds=self.config.timeout_seconds,
        )

    def is_configured(self) -> bool:
        # Hermes is still used for read-only portfolio and market data.  The
        # separate authenticated Bull Pilot client is mandatory for execution.
        return len(self.config.bridge_key) >= 32 and bool(self.config.account_number) and self.execution_gateway.ready

    def _call(self, tool: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Permit only read-only Hermes calls from Velez.

        All order progression is owned by Bull Pilot's authenticated immutable
        intent gateway; Velez never receives a direct placement capability.
        """
        if tool not in {"get_portfolio", "get_equity_positions", "get_equity_orders", "get_equity_quotes"}:
            raise RobinhoodBrokerError("direct_robinhood_tool_not_allowed")
        if not self.is_configured():
            raise RobinhoodBrokerError("robinhood_agentic_not_configured")
        response = requests.post(
            f"{self.config.bridge_url}/v1/tools/{tool}",
            headers={"Authorization": f"Bearer {self.config.bridge_key}"},
            json={"arguments": dict(arguments)},
            timeout=self.config.timeout_seconds,
        )
        try:
            payload = response.json()
        except ValueError as error:
            raise RobinhoodBrokerError("robinhood_bridge_invalid_json") from error
        if response.status_code != 200 or not isinstance(payload, Mapping) or payload.get("ok") is not True:
            raise RobinhoodBrokerError(f"robinhood_bridge_http_{response.status_code}")
        result = payload.get("result")
        if not isinstance(result, Mapping) or result.get("isError") is True:
            raise RobinhoodBrokerError("robinhood_mcp_result_rejected")
        structured = result.get("structuredContent")
        data = structured.get("data") if isinstance(structured, Mapping) else None
        if not isinstance(data, Mapping):
            raise RobinhoodBrokerError("robinhood_mcp_structured_data_invalid")
        return dict(data)

    def validate_connection(self) -> dict:
        if not self.is_configured():
            return {"ok": False, "reason": "missing_bridge_key_or_account"}
        try:
            response = requests.get(f"{self.config.bridge_url}/health", timeout=5)
            body = response.json()
            return {
                "ok": response.status_code == 200 and body.get("connected") is True,
                "paper": False,
                "agentic": True,
                "account_number_tail": self.config.account_number[-4:],
                "reason": body.get("last_error"),
            }
        except Exception as error:
            return {"ok": False, "reason": f"robinhood_health:{type(error).__name__}"}

    def get_account(self) -> dict:
        value = self._call("get_portfolio", {"account_number": self.config.account_number})
        buying_power = self._portfolio_scalar(value.get("buying_power"), "buying_power")
        return {
            "id": self.config.account_number,
            "equity": value.get("total_value") or value.get("equity") or value.get("portfolio_value"),
            "portfolio_value": value.get("total_value") or value.get("portfolio_value"),
            "cash": value.get("cash") or buying_power,
            "buying_power": buying_power,
            "status": "ACTIVE",
            "trading_blocked": False,
        }

    @staticmethod
    def _portfolio_scalar(value: Any, field: str) -> Any:
        """Unwrap a documented portfolio sub-object without guessing a value."""
        if isinstance(value, Mapping):
            return value.get(field)
        return value

    @staticmethod
    def _rows(value: Mapping[str, Any], *keys: str) -> list[dict]:
        for key in keys:
            rows = value.get(key)
            if isinstance(rows, list):
                return [dict(row) for row in rows if isinstance(row, Mapping)]
        return []

    def get_positions_raw(self) -> List[dict]:
        return self._rows(self._call("get_equity_positions", {"account_number": self.config.account_number}), "positions", "equity_positions", "results")

    def get_orders_raw(self, **_: Any) -> List[dict]:
        return self._rows(self._call("get_equity_orders", {"account_number": self.config.account_number}), "orders", "equity_orders", "results")

    def get_positions(self) -> List[Position]:
        positions = []
        for item in self.get_positions_raw():
            quantity = float(self._long_equity_quantity(item.get("quantity") or item.get("qty") or 0))
            positions.append(Position(
                symbol=str(item.get("symbol") or ""),
                qty=quantity,
                entry_price=float(item.get("average_buy_price") or item.get("avg_entry_price") or 0),
                entry_time=datetime.now(timezone.utc),
                stop_price=0.0,
                initial_stop=0.0,
                risk_per_share=0.0,
            ))
        return positions

    def submit_order(self, order: Order) -> Fill:
        result = self.submit_order_payload(self.order_payload_from_order(order))
        price = float(result.get("filled_avg_price") or order.limit_price or 0)
        return Fill(order=order, price=price, timestamp=datetime.now(timezone.utc), slippage=0.0, commission=0.0)

    def order_payload_from_order(self, order: Order, **_: Any) -> dict:
        return {
            "symbol": order.symbol,
            "qty": str(order.qty),
            "side": order.side.value,
            "type": order.order_type.value,
            "limit_price": order.limit_price,
            "time_in_force": "day",
            "client_order_id": str(order.metadata.get("client_order_id") or f"velez-rh-{sha256(str(order).encode()).hexdigest()[:24]}"),
        }

    def build_entry_payload(
        self,
        *,
        symbol: str,
        side: str,
        qty: float,
        order_type: str,
        entry_price: float | None,
        stop_price: float,
        client_order_id: str,
        time_in_force: str = "day",
        take_profit_price: float | None = None,
    ) -> dict:
        """Build a broker-neutral entry intent, never a Robinhood payload."""
        payload = {
            "symbol": symbol,
            "side": side,
            "qty": self._long_equity_quantity(qty),
            "type": order_type,
            "time_in_force": time_in_force,
            "client_order_id": client_order_id,
            "purpose": "entry",
            "protective_stop": {"stop_price": f"{stop_price:.2f}"},
        }
        if order_type == "limit" and entry_price is not None:
            payload["limit_price"] = f"{entry_price:.2f}"
        if take_profit_price is not None:
            payload["take_profit_price"] = f"{take_profit_price:.2f}"
        return payload

    def submit_order_payload(self, payload: Mapping[str, Any]) -> dict:
        """Prepare a broker-neutral intent through Bull Pilot only.

        Review-required requests intentionally stop at preparation.  A trusted
        operator approves through Bull Pilot's separate approval authority,
        then calls :meth:`submit_prepared_order` with only the opaque reference.
        """
        intent = self._broker_neutral_intent(payload)
        if not intent["symbol"] or float(intent["qty"]) <= 0 or not intent["client_order_id"]:
            raise RobinhoodBrokerError("invalid_order_payload")
        if intent.get("protective_stop") and not self.config.protective_stops_verified and not self.config.shadow_mode:
            raise RobinhoodBrokerError("robinhood_protective_stop_schema_not_verified")
        prepared = self.execution_gateway.prepare(intent, purpose=str(intent["purpose"]))
        if self.config.shadow_mode or not self.config.execution_enabled or prepared.get("approval_mode") == "review_required":
            return {"ok": True, "submitted": False, "status": "prepared_review_required", "prepared": prepared}
        # Rules authorization references and the explicit none override are
        # evaluated only by Bull Pilot.  Velez merely forwards its opaque ref.
        return self.submit_prepared_order(
            str(prepared.get("prepared_intent_id") or ""),
            str(prepared.get("intent_fingerprint") or ""),
            str(prepared["authorization_ref"]) if prepared.get("authorization_ref") else None,
        )

    def submit_prepared_order(self, prepared_intent_id: str, intent_fingerprint: str, authorization_ref: str | None) -> dict:
        if not prepared_intent_id or not intent_fingerprint:
            raise RobinhoodBrokerError("prepared_intent_reference_required")
        return self.execution_gateway.submit(
            prepared_intent_id=prepared_intent_id,
            intent_fingerprint=intent_fingerprint,
            authorization_ref=authorization_ref,
        )

    @staticmethod
    def _broker_neutral_intent(payload: Mapping[str, Any]) -> dict[str, Any]:
        result = {
            "symbol": str(payload.get("symbol") or "").upper(),
            "side": str(payload.get("side") or "").lower(),
            "qty": RobinhoodAgenticBroker._long_equity_quantity(payload.get("qty") or payload.get("quantity") or ""),
            "type": str(payload.get("type") or payload.get("order_type") or "market").lower(),
            "time_in_force": str(payload.get("time_in_force") or "day").lower(),
            "client_order_id": str(payload.get("client_order_id") or ""),
            "purpose": str(payload.get("purpose") or "entry").lower(),
        }
        for key in ("limit_price", "stop_price", "take_profit_price", "protective_stop", "_bullwarden"):
            if key in payload:
                result[key] = payload[key]
        return result

    @staticmethod
    def _long_equity_quantity(value: Any) -> str:
        try:
            quantity = Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError) as error:
            raise RobinhoodBrokerError("invalid_fractional_long_equity_quantity") from error
        if quantity <= 0:
            raise RobinhoodBrokerError("invalid_fractional_long_equity_quantity")
        return format(quantity, ".4f")

    def cancel_order(self, order_id: str) -> dict:
        raise RobinhoodBrokerError("direct_robinhood_cancellation_disabled_use_bullpilot_execution_gateway")

    def cancel_all_orders(self) -> dict:
        raise RobinhoodBrokerError("direct_robinhood_cancellation_disabled_use_bullpilot_execution_gateway")

    def submit_standalone_stop_with_retry(
        self,
        *,
        symbol: str,
        qty: Any,
        side: str,
        stop_price: float,
        client_order_id: str,
    ) -> dict:
        """Verify an attached stop, or add a risk-reducing stop once the fill is visible."""
        symbol = symbol.upper()
        stop_side = "sell" if side == "buy" else "buy"
        for item in self.get_orders_raw(status="open"):
            item_type = str(item.get("type") or item.get("order_type") or "").lower()
            item_symbol = str(item.get("symbol") or "").upper()
            candidate = float(item.get("stop_price") or 0)
            if item_symbol == symbol and item_type in {"stop", "stop_limit"} and abs(candidate - stop_price) < 0.011:
                return {"ok": True, "verified": True, "status": "existing_protective_stop"}
        if not self.config.protective_stops_verified:
            raise RobinhoodBrokerError("robinhood_protective_stop_schema_not_verified")
        result = self.submit_order_payload({
            "symbol": symbol,
            "qty": str(qty),
            "side": stop_side,
            "type": "stop",
            "stop_price": f"{stop_price:.2f}",
            "time_in_force": "gtc",
            "client_order_id": client_order_id,
            "purpose": "protective_stop",
        })
        return {**result, "verified": True}

    def get_portfolio_history_raw(self, **_: Any) -> dict:
        return {}

    def get_activities_raw(self, **_: Any) -> List[dict]:
        return []

    def get_all_activities_raw(self, **_: Any) -> List[dict]:
        return []

    def close(self) -> None:
        return None

    def get_latest_bar(self, symbol: str) -> Bar:
        quote = self._call("get_equity_quotes", {"symbols": [symbol]})
        rows = self._rows(quote, "quotes", "results")
        value = rows[0] if rows else quote
        if isinstance(value.get("quote"), Mapping):
            value = value["quote"]
        price = float(value.get("last_trade_price") or value.get("mark_price") or value.get("price") or 0)
        return Bar(timestamp=datetime.now(timezone.utc), open=price, high=price, low=price, close=price, volume=0)
