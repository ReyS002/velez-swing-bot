from __future__ import annotations

from typing import Callable, Dict, List

from .base import BrokerAdapter
from ..core.execution import ExecutionSimulator
from ..core.portfolio import Portfolio
from ..core.types import Order, Fill, Bar, Position


class PaperBroker(BrokerAdapter):
    def __init__(
        self,
        *,
        execution: ExecutionSimulator,
        price_provider: Callable[[str], float],
        contract_multipliers: Dict[str, float],
        starting_cash: float,
    ) -> None:
        self.execution = execution
        self.price_provider = price_provider
        self.contract_multipliers = contract_multipliers
        self.portfolio = Portfolio(cash=starting_cash)

    def submit_order(self, order: Order) -> Fill:
        price = self.price_provider(order.symbol)
        fill = self.execution.fill_at_price(
            order=order,
            price=price,
            timestamp=order.timestamp,
            contract_multiplier=self.contract_multipliers.get(order.symbol, 1.0),
        )
        self.portfolio.apply_fill(fill, self.contract_multipliers.get(order.symbol, 1.0))
        return fill

    def get_positions(self) -> List[Position]:
        return list(self.portfolio.positions.values())

    def get_latest_bar(self, symbol: str) -> Bar:
        raise NotImplementedError("Live bar feed not implemented for PaperBroker.")

    def close(self) -> None:
        return None
