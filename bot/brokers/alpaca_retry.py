import time
import logging
from typing import Optional, Dict, Any

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

    def submit_standalone_stop_with_retry(
        self,
        symbol: str,
        qty: int,
        side: str,
        stop_price: float,
        client_order_id: Optional[str] = None,
        max_retries: int = 3,
        backoff_factor: float = 1.5
    ) -> Dict[str, Any]:
        """
        Submits an independent stop order to Alpaca with exponential backoff retry logic.
        Ensures that if bracket/OTO stop attachment fails, the standalone stop is guaranteed to be placed.
        """
        stop_side = "buy" if side.lower() == "sell" else "sell"
        
        payload = {
            "symbol": symbol,
            "qty": str(qty),
            "side": stop_side,
            "type": "stop",
            "time_in_force": "gtc",
            "stop_price": self._price(stop_price),
        }
        if client_order_id:
            payload["client_order_id"] = f"{client_order_id}-stop"

        last_exception = None
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Submitting standalone stop for {symbol} (Attempt {attempt}/{max_retries}) at {stop_price}")
                response = self.submit_order_payload(payload)
                if response and (response.get("id") or response.get("status") in ["new", "accepted", "pending_new"]):
                    logger.info(f"Successfully attached standalone stop for {symbol}, order ID: {response.get('id')}")
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
