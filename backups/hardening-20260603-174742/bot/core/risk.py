from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from .types import Position, Side
from .utils import safe_div


@dataclass
class RiskStatus:
    allowed: bool
    reason: str


class RiskManager:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.current_day: Optional[date] = None
        self.daily_loss: float = 0.0
        self.consecutive_losses: int = 0
        self.api_errors: int = 0
        self.kill_switch: bool = False

    def reset_day(self, new_day: date) -> None:
        self.current_day = new_day
        self.daily_loss = 0.0
        self.consecutive_losses = 0

    def update_after_trade(self, pnl: float) -> None:
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        self.daily_loss += pnl
        if self.consecutive_losses >= self.config["max_consecutive_losses"]:
            self.kill_switch = True

    def register_api_error(self) -> None:
        self.api_errors += 1
        max_errors = self.config.get("max_api_errors", 5)
        if self.api_errors >= max_errors:
            self.kill_switch = True

    def check_limits(self, equity: float, open_positions: int) -> RiskStatus:
        if self.kill_switch:
            return RiskStatus(False, "kill_switch")
        if open_positions >= self.config["max_open_positions"]:
            return RiskStatus(False, "max_open_positions")
        max_daily_loss = -equity * self.config["max_daily_loss_pct"]
        if self.daily_loss <= max_daily_loss:
            return RiskStatus(False, "max_daily_loss")
        return RiskStatus(True, "ok")

    def check_circuit_breaker(self, atr_percent: Optional[float]) -> bool:
        if atr_percent is None:
            return False
        return atr_percent >= self.config.get("circuit_breaker_atr_pct", 1.0)

    def calculate_position_size(
        self,
        *,
        equity: float,
        entry_price: float,
        stop_price: float,
        contract_multiplier: float,
        max_order_qty: int,
        max_leverage: float,
    ) -> int:
        risk_per_trade = equity * self.config["risk_per_trade"]
        stop_distance = abs(entry_price - stop_price)
        risk_per_unit = stop_distance * contract_multiplier
        if risk_per_unit <= 0:
            return 0
        raw_qty = int(risk_per_trade / risk_per_unit)
        if raw_qty <= 0:
            return 0
        position_value = raw_qty * entry_price * contract_multiplier
        max_value = equity * max_leverage
        if position_value > max_value:
            raw_qty = int(max_value / (entry_price * contract_multiplier))
        return max(0, min(raw_qty, max_order_qty))

    def calculate_fixed_risk_position_size(
        self,
        *,
        max_dollar_risk: float,
        entry_price: float,
        stop_price: float,
        contract_multiplier: float,
        max_order_qty: int,
        equity: Optional[float] = None,
        max_leverage: Optional[float] = None,
    ) -> int:
        stop_distance = abs(entry_price - stop_price)
        risk_per_unit = stop_distance * contract_multiplier
        if max_dollar_risk <= 0 or risk_per_unit <= 0:
            return 0

        raw_qty = int(max_dollar_risk / risk_per_unit)
        if raw_qty <= 0:
            return 0

        if equity is not None and max_leverage is not None:
            max_value = equity * max_leverage
            position_value = raw_qty * entry_price * contract_multiplier
            if position_value > max_value:
                raw_qty = int(max_value / (entry_price * contract_multiplier))

        return max(0, min(raw_qty, max_order_qty))

    def calculate_pyramid_add_size(self, *, current_qty: int, original_core_qty: Optional[int] = None) -> int:
        add_qty = int(abs(current_qty) * self.config.get("pyramid_add_fraction", 0.5))
        if original_core_qty is not None:
            add_qty = min(add_qty, max(0, original_core_qty - abs(current_qty)))
        return max(0, add_qty)

    def initial_stop(
        self,
        *,
        side: Side,
        entry_price: float,
        atr: Optional[float],
        swing_level: Optional[float],
        config: dict,
    ) -> Optional[float]:
        stop_type = config.get("stop_type", "atr")
        atr_mult = config.get("stop_atr_mult", 2.0)
        if stop_type == "structure" and swing_level is not None:
            return swing_level
        if atr is None:
            return None
        if side == Side.BUY:
            return entry_price - atr_mult * atr
        return entry_price + atr_mult * atr

    def update_trailing_stop(
        self,
        *,
        position: Position,
        close: float,
        sma20: Optional[float],
        atr: Optional[float],
        config: dict,
    ) -> Optional[float]:
        trail_type = config.get("trail_type", "atr")
        trail_atr_mult = config.get("trail_atr_mult", 2.5)
        debounce = config.get("trail_debounce", 2)

        if trail_type == "atr" and atr is not None:
            if position.qty > 0:
                new_stop = close - trail_atr_mult * atr
                return max(position.stop_price, new_stop)
            new_stop = close + trail_atr_mult * atr
            return min(position.stop_price, new_stop)

        if trail_type == "sma20" and sma20 is not None:
            if position.qty > 0:
                if close < sma20:
                    position.trail_breach_count += 1
                else:
                    position.trail_breach_count = 0
                if position.trail_breach_count >= debounce:
                    return close
            else:
                if close > sma20:
                    position.trail_breach_count += 1
                else:
                    position.trail_breach_count = 0
                if position.trail_breach_count >= debounce:
                    return close

        return position.stop_price

    def time_stop_trigger(
        self,
        *,
        position: Position,
        atr: Optional[float],
        close: float,
        config: dict,
    ) -> bool:
        if not config.get("enabled", False):
            return False
        if atr is None:
            return False
        bars = config.get("bars", 0)
        min_move = config.get("min_move_atr", 1.0)
        if position.bars_held < bars:
            return False
        move = (close - position.entry_price) if position.qty > 0 else (position.entry_price - close)
        return move < (min_move * atr)

    def position_r_multiple(self, position: Position, price: float) -> float:
        if position.risk_per_share <= 0:
            return 0.0
        move = (price - position.entry_price) if position.qty > 0 else (position.entry_price - price)
        return safe_div(move, position.risk_per_share)
