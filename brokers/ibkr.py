from __future__ import annotations

from .base import BrokerAdapter
from ..core.types import Order, Fill, Bar, Position


class IBKRBroker(BrokerAdapter):
    def submit_order(self, order: Order) -> Fill:
        raise NotImplementedError("IBKR broker adapter is a stub. Implement using ib_insync or official API.")

    def get_positions(self) -> list[Position]:
        raise NotImplementedError("IBKR broker adapter is a stub.")

    def get_latest_bar(self, symbol: str) -> Bar:
        raise NotImplementedError("IBKR broker adapter is a stub.")

    def close(self) -> None:
        return None
