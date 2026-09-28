from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from ..core.types import Fill, Order, Position

logger = logging.getLogger("TradovateBroker")


@dataclass(frozen=True)
class TradovateConfig:
    username: str
    password: str
    app_id: str
    client_secret: str
    base_url: str = "https://demo.tradovateapi.com/v1"
    ws_url: str = "wss://demo.tradovate.com/v1/websocket"
    timeout_seconds: int = 20
    demo: bool = True
    max_trailing_drawdown: float = 2500.0  # Apex default max trailing drawdown
    daily_profit_cap: float = 0.0          # Consistency rule cap (0 = disabled)
    eod_flatten_time_et: str = "15:55"     # EOD close cutoff (ET)

    @classmethod
    def from_env(cls) -> "TradovateConfig":
        demo_env = os.getenv("TRADOVATE_DEMO", "true").lower() in {"1", "true", "yes", "on"}
        base_url = "https://demo.tradovateapi.com/v1" if demo_env else "https://live.tradovateapi.com/v1"
        ws_url = "wss://demo.tradovate.com/v1/websocket" if demo_env else "wss://live.tradovate.com/v1/websocket"
        return cls(
            username=os.getenv("TRADOVATE_USER", os.getenv("TRADOVATE_USERNAME", "")),
            password=os.getenv("TRADOVATE_PASSWORD", ""),
            app_id=os.getenv("TRADOVATE_APP_ID", "VelezBot"),
            client_secret=os.getenv("TRADOVATE_SECRET", os.getenv("TRADOVATE_CLIENT_SECRET", "")),
            base_url=os.getenv("TRADOVATE_BASE_URL", base_url),
            ws_url=os.getenv("TRADOVATE_WS_URL", ws_url),
            demo=demo_env,
            max_trailing_drawdown=float(os.getenv("PROP_MAX_TRAILING_DRAWDOWN", "2500.0")),
            daily_profit_cap=float(os.getenv("PROP_DAILY_PROFIT_CAP", "0.0")),
            eod_flatten_time_et=os.getenv("PROP_EOD_FLATTEN_TIME_ET", "15:55"),
        )


class TradovateBroker:
    """REST & WebSocket Broker Adapter for Tradovate / Prop Firm Accounts (Apex, Topstep, etc.).
    Fully compatible with Velez Trading Bot & Swing Bot broker interfaces.
    Includes built-in Prop Firm Risk Guardrails:
      - Trailing Drawdown High-Water Mark tracking
      - Consistency rule profit limits
      - EOD flattening window check
    """

    def __init__(self, config: Optional[TradovateConfig] = None) -> None:
        self.config = config or TradovateConfig.from_env()
        self.access_token: Optional[str] = None
        self.token_expiry: float = 0.0
        self.account_id: Optional[int] = None
        self.account_name: str = ""
        
        # Prop Guardrail State
        self.peak_equity: float = 0.0
        self.day_start_equity: float = 0.0
        self.breach_kill_switch: bool = False
        self.breach_reason: str = ""

    def is_configured(self) -> bool:
        return bool(self.config.username and self.config.password and self.config.app_id)

    def tradovate_symbol(self, symbol: str) -> str:
        if not symbol:
            return ""
        symbol = str(symbol).upper().strip()
        symbol = re.sub(r'^[A-Z0-9_]+:', '', symbol)
        symbol = re.sub(r'\d+!$', '', symbol)
        symbol = re.sub(r'!$', '', symbol)
        
        mapping_str = os.getenv("TRADOVATE_SYMBOL_MAP", "{}")
        try:
            mapping = json.loads(mapping_str)
            if isinstance(mapping, dict) and symbol in mapping:
                return str(mapping[symbol])
        except Exception:
            pass
        return symbol

    def _inverse_tradovate_symbol(self, symbol: str) -> str:
        if not symbol:
            return ""
        symbol = str(symbol).upper().strip()
        
        mapping_str = os.getenv("TRADOVATE_SYMBOL_MAP", "{}")
        try:
            mapping = json.loads(mapping_str)
            if isinstance(mapping, dict):
                for root, mapped in mapping.items():
                    if str(mapped).upper().strip() == symbol:
                        return root
        except Exception:
            pass
        return symbol

    def _authenticate(self) -> None:
        if self.access_token and time.time() < self.token_expiry:
            return
        if not self.is_configured():
            raise RuntimeError("Tradovate credentials are missing.")

        url = f"{self.config.base_url.rstrip('/')}/auth/accesstokenrequest"
        payload = {
            "name": self.config.username,
            "password": self.config.password,
            "appId": self.config.app_id,
            "appVersion": "1.0",
            "cid": self.config.app_id,
            "sec": self.config.client_secret,
        }
        resp = requests.post(url, json=payload, timeout=self.config.timeout_seconds)
        if resp.status_code >= 300:
            raise RuntimeError(f"Tradovate auth failed ({resp.status_code}): {resp.text}")
        data = resp.json()
        self.access_token = data.get("accessToken")
        # Token valid for ~24 hours; set 23-hour buffer
        self.token_expiry = time.time() + 82800
        self._sync_account_id()

    def _headers(self) -> dict:
        self._authenticate()
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _sync_account_id(self) -> None:
        if not self.access_token:
            return
        url = f"{self.config.base_url.rstrip('/')}/account/list"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        resp = requests.get(url, headers=headers, timeout=self.config.timeout_seconds)
        if resp.status_code == 200:
            accounts = resp.json()
            if accounts and isinstance(accounts, list):
                self.account_id = accounts[0].get("id")
                self.account_name = str(accounts[0].get("name", ""))

    def validate_connection(self) -> dict:
        if not self.is_configured():
            return {"ok": False, "reason": "missing_credentials"}
        try:
            account = self.get_account()
            return {
                "ok": True,
                "account_status": "active" if self.account_id else "unknown",
                "trading_blocked": self.breach_kill_switch,
                "account_number_tail": str(self.account_name)[-4:] if self.account_name else str(self.account_id)[-4:],
                "paper": self.config.demo,
                "prop_guardrails": {
                    "trailing_drawdown_limit": self.config.max_trailing_drawdown,
                    "peak_equity": self.peak_equity,
                    "kill_switch": self.breach_kill_switch,
                    "reason": self.breach_reason,
                },
            }
        except Exception as exc:
            return {"ok": False, "reason": str(exc)}

    def get_account(self) -> dict:
        self._authenticate()
        if not self.account_id:
            self._sync_account_id()
        url = f"{self.config.base_url.rstrip('/')}/account/item"
        params = {"id": self.account_id}
        resp = requests.get(url, headers=self._headers(), params=params, timeout=self.config.timeout_seconds)
        if resp.status_code == 200:
            acc = resp.json()
            # Calculate equity and sync prop drawdown risk
            cash_bal = float(acc.get("balance", 0.0) or 0.0)
            self._update_prop_drawdown_risk(cash_bal)
            return {
                "id": self.account_id,
                "account_number": self.account_name or str(self.account_id),
                "status": "ACTIVE",
                "equity": str(cash_bal),
                "last_equity": str(self.day_start_equity or cash_bal),
                "buying_power": str(cash_bal),
                "cash": str(cash_bal),
                "portfolio_value": str(cash_bal),
                "trading_blocked": self.breach_kill_switch,
            }
        return {"id": self.account_id, "equity": "0.0", "trading_blocked": self.breach_kill_switch}

    def _update_prop_drawdown_risk(self, current_equity: float) -> None:
        if current_equity <= 0:
            return
        if self.day_start_equity == 0.0:
            self.day_start_equity = current_equity
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity

        # Trailing High-Water Mark Drawdown Check
        drawdown = self.peak_equity - current_equity
        if drawdown >= self.config.max_trailing_drawdown and self.config.max_trailing_drawdown > 0:
            self.breach_kill_switch = True
            self.breach_reason = f"Prop Trailing Drawdown Breached (${drawdown:.2f} >= ${self.config.max_trailing_drawdown:.2f})"
            logger.critical(self.breach_reason)

        # Consistency Daily Profit Cap Check
        if self.config.daily_profit_cap > 0:
            daily_pnl = current_equity - self.day_start_equity
            if daily_pnl >= self.config.daily_profit_cap:
                self.breach_kill_switch = True
                self.breach_reason = f"Daily Profit Target Cap Reached (${daily_pnl:.2f} >= ${self.config.daily_profit_cap:.2f})"

    def check_eod_flatness_window(self) -> bool:
        """Returns True if within EOD cutoff window where new positions are blocked & existing should flat."""
        try:
            import zoneinfo
            et_zone = zoneinfo.ZoneInfo("America/New_York")
            now_et = datetime.now(et_zone)
            eod_parts = [int(p) for p in self.config.eod_flatten_time_et.split(":")]
            eod_time = now_et.replace(hour=eod_parts[0], minute=eod_parts[1], second=0, microsecond=0)
            if now_et >= eod_time and now_et.hour < 18:
                return True
        except Exception:
            pass
        return False

    def check_prop_trade_allowed(self) -> tuple[bool, str]:
        if self.breach_kill_switch:
            return False, f"Prop Guardrail Active: {self.breach_reason}"
        if self.check_eod_flatness_window():
            return False, f"EOD Flatness Window Active (after {self.config.eod_flatten_time_et} ET)"
        return True, "ok"

    def get_positions_raw(self) -> List[dict]:
        self._authenticate()
        url = f"{self.config.base_url.rstrip('/')}/position/list"
        resp = requests.get(url, headers=self._headers(), timeout=self.config.timeout_seconds)
        if resp.status_code == 200:
            positions = resp.json()
            raw_list = []
            if isinstance(positions, list):
                for p in positions:
                    net_pos = int(p.get("netPos", 0))
                    if net_pos != 0:
                        raw_list.append({
                            "symbol": self._inverse_tradovate_symbol(p.get("contractId") or p.get("symbol", "")),
                            "qty": str(abs(net_pos)),
                            "side": "long" if net_pos > 0 else "short",
                            "avg_entry_price": str(p.get("avgPrice", 0.0)),
                            "market_value": str(float(p.get("avgPrice", 0.0)) * abs(net_pos)),
                        })
            return raw_list
        return []

    def get_orders_raw(
        self,
        *,
        status: str = "open",
        limit: int = 100,
        direction: str = "desc",
        nested: bool = True,
        symbols: Optional[str] = None,
    ) -> List[dict]:
        self._authenticate()
        url = f"{self.config.base_url.rstrip('/')}/order/list"
        resp = requests.get(url, headers=self._headers(), timeout=self.config.timeout_seconds)
        if resp.status_code == 200:
            orders = resp.json()
            out = []
            if isinstance(orders, list):
                for o in orders:
                    ord_status = str(o.get("ordStatus", "")).lower()
                    if status == "open" and ord_status not in {"working", "accepted", "pending"}:
                        continue
                    out.append({
                        "id": str(o.get("id")),
                        "client_order_id": str(o.get("clOrdId", f"tradovate-{o.get('id')}")),
                        "symbol": self._inverse_tradovate_symbol(str(o.get("symbol", ""))),
                        "side": "buy" if o.get("action") == "Buy" else "sell",
                        "qty": str(o.get("orderQty", 1)),
                        "status": ord_status,
                    })
            return out[:limit]
        return []

    def get_portfolio_history_raw(self, *, period: str = "1M", timeframe: str = "1D") -> dict:
        self._authenticate()
        cash = self.day_start_equity or self.peak_equity or 100000.0
        return {
            "equity": [cash],
            "profit_loss": [0.0],
            "profit_loss_pct": [0.0],
            "timeframe": timeframe,
        }

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
        allowed, reason = self.check_prop_trade_allowed()
        if not allowed:
            raise RuntimeError(f"Order rejected by Prop Guardrails: {reason}")
        if qty <= 0:
            raise ValueError("qty must be positive")

        return {
            "symbol": self.tradovate_symbol(symbol),
            "action": "Buy" if side.lower() == "buy" else "Sell",
            "orderQty": qty,
            "orderType": "Market" if order_type.lower() == "market" else "Limit",
            "price": entry_price if order_type.lower() == "limit" else None,
            "stopPrice": stop_price,
            "takeProfitPrice": take_profit_price,
            "client_order_id": client_order_id or f"velez-{uuid.uuid4().hex[:20]}",
            "isAutomated": True,
        }

    def submit_order_payload(self, payload: dict) -> dict:
        allowed, reason = self.check_prop_trade_allowed()
        if not allowed:
            raise RuntimeError(f"Prop Rule Guardrail Active: {reason}")

        self._authenticate()
        url = f"{self.config.base_url.rstrip('/')}/order/placeorder"
        body = {
            "accountId": self.account_id,
            "symbol": payload.get("symbol"),
            "action": payload.get("action", "Buy"),
            "orderQty": int(payload.get("orderQty", 1)),
            "orderType": payload.get("orderType", "Market"),
            "isAutomated": True,
        }
        if payload.get("price"):
            body["price"] = float(payload["price"])

        resp = requests.post(url, headers=self._headers(), json=body, timeout=self.config.timeout_seconds)
        if resp.status_code >= 300:
            raise RuntimeError(f"Tradovate placeOrder failed: {resp.status_code} {resp.text}")

        res = resp.json()
        order_id = res.get("orderId") or res.get("id") or str(uuid.uuid4())
        
        # Attach bracket stop-loss if stopPrice provided
        stop_price = payload.get("stopPrice")
        if stop_price:
            stop_action = "Sell" if payload.get("action") == "Buy" else "Buy"
            stop_body = {
                "accountId": self.account_id,
                "symbol": payload.get("symbol"),
                "action": stop_action,
                "orderQty": int(payload.get("orderQty", 1)),
                "orderType": "Stop",
                "stopPrice": float(stop_price),
                "isAutomated": True,
            }
            try:
                requests.post(url, headers=self._headers(), json=stop_body, timeout=self.config.timeout_seconds)
            except Exception as e:
                logger.error(f"Failed to place Tradovate protective stop: {e}")

        return {
            "id": str(order_id),
            "status": "accepted",
            "client_order_id": payload.get("client_order_id"),
            "filled_avg_price": payload.get("price") or 0.0,
        }

    def cancel_order(self, order_id: str) -> dict:
        self._authenticate()
        url = f"{self.config.base_url.rstrip('/')}/order/cancelorder"
        body = {"orderId": int(order_id)}
        resp = requests.post(url, headers=self._headers(), json=body, timeout=self.config.timeout_seconds)
        if resp.status_code == 200:
            return {"id": order_id, "status": "canceled"}
        return {"id": order_id, "status": "failed", "reason": resp.text}

    def cancel_all_orders(self) -> dict:
        open_orders = self.get_orders_raw(status="open")
        canceled = []
        for o in open_orders:
            try:
                self.cancel_order(o["id"])
                canceled.append(o["id"])
            except Exception:
                pass
        return {"canceled_count": len(canceled), "canceled_ids": canceled}

    def close(self) -> None:
        pass
