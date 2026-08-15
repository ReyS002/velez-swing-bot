import logging
import time
import uuid
from typing import Any, Dict, Iterator, Optional

logger = logging.getLogger("alpaca_stop_retry")

class AlpacaStopRetryMixin:
    """
    Mixin for AlpacaBroker to provide robust standalone stop-loss submission
    with exponential backoff retry logic.
    """
    def _price(self, price: float) -> str:
        return f"{float(price):.2f}"

    def submit_order_payload(self, payload: dict) -> dict:
        raise NotImplementedError

    def _position_matches_entry_side(self, symbol: str, entry_side: str) -> Optional[bool]:
        """Return whether Alpaca still reports the expected open position."""
        get_positions = getattr(self, "get_positions_raw", None)
        if not callable(get_positions):
            return None
        expected_position_side = "long" if entry_side == "buy" else "short"
        for position in get_positions() or []:
            if str(position.get("symbol") or "").upper() != symbol.upper():
                continue
            if str(position.get("side") or "").lower() == expected_position_side:
                try:
                    if float(position.get("qty") or 0) != 0:
                        return True
                except (TypeError, ValueError):
                    continue
        return False

    @staticmethod
    def _iter_orders(orders: object) -> Iterator[dict]:
        if not isinstance(orders, list):
            return
        for order in orders:
            if not isinstance(order, dict):
                continue
            yield order
            legs = order.get("legs")
            if isinstance(legs, list):
                yield from AlpacaStopRetryMixin._iter_orders(legs)

    def _existing_protective_stop(self, symbol: str, stop_side: str) -> Optional[dict]:
        get_orders = getattr(self, "get_orders_raw", None)
        if not callable(get_orders):
            return None
        orders = get_orders(status="open", symbols=symbol, nested=True)
        for order in self._iter_orders(orders):
            if str(order.get("symbol") or "").upper() != symbol.upper():
                continue
            if str(order.get("side") or "").lower() != stop_side:
                continue
            if str(order.get("type") or "").lower() in {"stop", "stop_limit", "trailing_stop"}:
                return order
        return None

    def submit_standalone_stop_with_retry(
        self,
        symbol: str,
        qty: Any,
        side: str,
        stop_price: float,
        client_order_id: Optional[str] = None,
        max_retries: int = 3,
        backoff_factor: float = 1.5
    ) -> Dict[str, Any]:
        """Submit and reconcile an independent stop after a confirmed entry."""
        entry_side = str(side or "").lower()
        if entry_side not in {"buy", "sell"}:
            raise ValueError("side must be buy or sell")
        try:
            if float(qty) <= 0 or float(stop_price) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError("qty and stop_price must be positive") from None
        stop_side = "buy" if entry_side == "sell" else "sell"
        position_state = self._position_matches_entry_side(symbol, entry_side)
        if position_state is False:
            return {"status": "skipped_no_open_position", "symbol": symbol, "verified": True}
        base_client_order_id = str(client_order_id or f"stop-{symbol.lower()}-{uuid.uuid4().hex[:20]}")
        stop_client_order_id = f"{base_client_order_id[:43]}-stop"

        payload = {
            "symbol": symbol,
            "qty": str(qty),
            "side": stop_side,
            "type": "stop",
            "time_in_force": "gtc",
            "stop_price": self._price(stop_price),
        }
        payload["client_order_id"] = stop_client_order_id

        last_exception = None
        for attempt in range(1, max_retries + 1):
            try:
                existing = self._existing_protective_stop(symbol, stop_side)
                if existing is not None:
                    return {"id": existing.get("id"), "status": "verified_existing", "verified": True, "order": existing}
                logger.info(f"Submitting standalone stop for {symbol} (Attempt {attempt}/{max_retries}) at {stop_price}")
                response = self.submit_order_payload(payload)
                if callable(getattr(self, "get_orders_raw", None)):
                    existing = self._existing_protective_stop(symbol, stop_side)
                    if existing is not None:
                        return {"id": existing.get("id") or (response or {}).get("id"), "status": "verified", "verified": True, "order": existing, "submission": response}
                    logger.warning("Stop submission for %s was not yet visible in Alpaca open orders", symbol)
                elif response and (response.get("id") or response.get("status") in {"new", "accepted", "pending_new"}):
                    return response
                else:
                    logger.warning(f"Stop submission response lacked valid order ID for {symbol}: {response}")
            except Exception as e:
                last_exception = e
                logger.warning(f"Attempt {attempt} failed to submit stop for {symbol}: {e}")

            if attempt < max_retries:
                sleep_time = backoff_factor ** attempt
                time.sleep(sleep_time)

        raise RuntimeError(f"Failed to submit standalone stop for {symbol} after {max_retries} attempts. Last error: {last_exception}")
