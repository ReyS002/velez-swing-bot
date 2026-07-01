from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

from .types import Regime, NarrowWideState


@dataclass
class StateSnapshot:
    regime: Regime
    narrow_wide: NarrowWideState
    transition_n2w: bool
    spread: Optional[float]
    atr_percent: Optional[float]


class StateMachine:
    def __init__(self, *, narrow_threshold: float, wide_threshold: float, narrow_bars: int) -> None:
        self.narrow_threshold = narrow_threshold
        self.wide_threshold = wide_threshold
        self.narrow_bars = narrow_bars
        self._spread_window: Deque[float] = deque(maxlen=narrow_bars)
        self._atrp_window: Deque[float] = deque(maxlen=narrow_bars)
        self.state: NarrowWideState = NarrowWideState.UNKNOWN

    def _narrow_condition(self) -> bool:
        if len(self._spread_window) < self.narrow_bars:
            return False
        spread_ok = max(self._spread_window) < self.narrow_threshold
        atrp_declining = self._atrp_window[-1] < self._atrp_window[0]
        return spread_ok and atrp_declining

    def update(
        self,
        *,
        close: float,
        sma20: Optional[float],
        sma200: Optional[float],
        sma200_slope: Optional[float],
        atr: Optional[float],
        breakout_bar: bool,
    ) -> StateSnapshot:
        spread = None
        atr_percent = None
        if sma20 is not None and sma200 is not None and close > 0:
            spread = abs(sma20 - sma200) / close
            self._spread_window.append(spread)
        if atr is not None and close > 0:
            atr_percent = atr / close
            self._atrp_window.append(atr_percent)

        narrow_condition = self._narrow_condition()
        wide_condition = False
        if spread is not None:
            wide_condition = spread > self.wide_threshold
        if breakout_bar:
            wide_condition = True

        transition_n2w = False
        if self.state == NarrowWideState.UNKNOWN:
            self.state = NarrowWideState.NARROW if narrow_condition else NarrowWideState.WIDE
        elif self.state == NarrowWideState.NARROW:
            if wide_condition:
                self.state = NarrowWideState.WIDE
                transition_n2w = True
        elif self.state == NarrowWideState.WIDE:
            if narrow_condition:
                self.state = NarrowWideState.NARROW

        regime = Regime.NEUTRAL
        if sma200 is not None and sma200_slope is not None:
            if close > sma200 and sma200_slope > 0:
                regime = Regime.BULL
            elif close < sma200 and sma200_slope < 0:
                regime = Regime.BEAR

        return StateSnapshot(
            regime=regime,
            narrow_wide=self.state,
            transition_n2w=transition_n2w,
            spread=spread,
            atr_percent=atr_percent,
        )
