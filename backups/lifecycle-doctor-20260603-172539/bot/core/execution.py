from __future__ import annotations

from datetime import datetime
from typing import Optional

from .types import Order, OrderType, Fill


class ExecutionSimulator:
    def __init__(
        self,
        *,
        slippage_bps: float,
        commission_per_share: float,
        commission_per_contract: float,
    ) -> None:
        self.slippage_bps = slippage_bps
        self.commission_per_share = commission_per_share
        self.commission_per_contract = commission_per_contract

    def _apply_slippage(self, price: float, is_buy: bool) -> float:
        slippage = price * (self.slippage_bps / 10000.0)
        return price + slippage if is_buy else price - slippage

    def _commission(self, qty: int, contract_multiplier: float) -> float:
        if contract_multiplier > 1:
            return self.commission_per_contract * qty
        return self.commission_per_share * qty

    def fill_at_price(
        self,
        *,
        order: Order,
        price: float,
        timestamp: datetime,
        contract_multiplier: float,
    ) -> Fill:
        is_buy = order.side.value == "buy"
        fill_price = self._apply_slippage(price, is_buy)
        commission = self._commission(order.qty, contract_multiplier)
        slippage = abs(fill_price - price)
        return Fill(order=order, price=fill_price, timestamp=timestamp, slippage=slippage, commission=commission)

    def fill_order(
        self,
        *,
        order: Order,
        bar_open: float,
        bar_high: float,
        bar_low: float,
        timestamp: datetime,
        contract_multiplier: float,
    ) -> Optional[Fill]:
        is_buy = order.side.value == "buy"
        price: Optional[float] = None

        if order.order_type == OrderType.MARKET:
            price = bar_open
        elif order.order_type == OrderType.LIMIT:
            if order.limit_price is None:
                return None
            if is_buy and bar_low <= order.limit_price:
                price = order.limit_price
            elif (not is_buy) and bar_high >= order.limit_price:
                price = order.limit_price

        if price is None:
            return None

        fill_price = self._apply_slippage(price, is_buy)
        commission = self._commission(order.qty, contract_multiplier)
        slippage = abs(fill_price - price)

        return Fill(order=order, price=fill_price, timestamp=timestamp, slippage=slippage, commission=commission)
