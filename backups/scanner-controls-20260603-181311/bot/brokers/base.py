from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from ..core.types import Order, Fill, Bar, Position


class BrokerAdapter(ABC):
    @abstractmethod
    def submit_order(self, order: Order) -> Fill:
        raise NotImplementedError

    @abstractmethod
    def get_positions(self) -> List[Position]:
        raise NotImplementedError

    @abstractmethod
    def get_latest_bar(self, symbol: str) -> Bar:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError
