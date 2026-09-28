from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .types import Position, Fill


@dataclass
class Portfolio:
    cash: float
    positions: Dict[str, Position] = field(default_factory=dict)
    trades: List[Dict] = field(default_factory=list)

    def get_position(self, symbol: str) -> Optional[Position]:
        return self.positions.get(symbol)

    def open_positions_count(self) -> int:
        return sum(1 for p in self.positions.values() if p.qty != 0)

    def apply_fill(self, fill: Fill, contract_multiplier: float) -> tuple[float, bool]:
        order = fill.order
        signed_qty = order.qty if order.side.value == "buy" else -order.qty
        cost = fill.price * order.qty * contract_multiplier
        commission = fill.commission

        if signed_qty > 0:
            self.cash -= cost + commission
        else:
            self.cash += cost - commission

        position = self.positions.get(order.symbol)
        realized_pnl = 0.0

        if position is None:
            self.positions[order.symbol] = Position(
                symbol=order.symbol,
                qty=signed_qty,
                entry_price=fill.price,
                entry_time=fill.timestamp,
                stop_price=fill.order.metadata.get("stop_price", fill.price),
                initial_stop=fill.order.metadata.get("stop_price", fill.price),
                risk_per_share=fill.order.metadata.get("risk_per_share", 0.0),
            )
            return realized_pnl, False

        # Same direction add
        if position.qty * signed_qty > 0:
            total_qty = position.qty + signed_qty
            position.entry_price = (position.entry_price * abs(position.qty) + fill.price * abs(signed_qty)) / abs(total_qty)
            position.qty = total_qty
            return realized_pnl, False

        # Reduce or reverse
        closing_qty = min(abs(position.qty), abs(signed_qty))
        if position.qty > 0:
            realized_pnl += (fill.price - position.entry_price) * closing_qty * contract_multiplier
        else:
            realized_pnl += (position.entry_price - fill.price) * closing_qty * contract_multiplier

        position.qty += signed_qty
        position_closed = False
        if position.qty == 0:
            self.positions.pop(order.symbol, None)
            position_closed = True
        else:
            position.entry_price = fill.price
            position.entry_time = fill.timestamp
        return realized_pnl, position_closed

    def equity(self, prices: Dict[str, float], contract_multipliers: Dict[str, float]) -> float:
        equity = self.cash
        for symbol, position in self.positions.items():
            price = prices.get(symbol)
            if price is None:
                continue
            mult = contract_multipliers.get(symbol, 1.0)
            equity += position.qty * price * mult
        return equity
