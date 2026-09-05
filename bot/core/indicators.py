from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

from .types import Bar
from .utils import safe_div


@dataclass
class RollingSMA:
    window: int
    values: Deque[float] = None
    _sum: float = 0.0

    def __post_init__(self) -> None:
        self.values = deque(maxlen=self.window)

    def update(self, value: float) -> Optional[float]:
        if len(self.values) == self.window:
            self._sum -= self.values[0]
        self.values.append(value)
        self._sum += value
        if len(self.values) < self.window:
            return None
        return self._sum / self.window


@dataclass
class RollingEMA:
    window: int
    values: Deque[float] = None
    ema: Optional[float] = None

    def __post_init__(self) -> None:
        self.values = deque(maxlen=self.window)

    def update(self, value: float) -> Optional[float]:
        if self.ema is None:
            self.values.append(value)
            if len(self.values) < self.window:
                return None
            self.ema = sum(self.values) / self.window
            return self.ema

        alpha = 2.0 / (self.window + 1.0)
        self.ema = alpha * value + (1 - alpha) * self.ema
        return self.ema


@dataclass
class RollingATR:
    window: int
    prev_close: Optional[float] = None
    atr: Optional[float] = None
    trs: Deque[float] = None

    def __post_init__(self) -> None:
        self.trs = deque(maxlen=self.window)

    def _true_range(self, bar: Bar) -> float:
        if self.prev_close is None:
            return bar.high - bar.low
        return max(
            bar.high - bar.low,
            abs(bar.high - self.prev_close),
            abs(bar.low - self.prev_close),
        )

    def update(self, bar: Bar) -> Optional[float]:
        tr = self._true_range(bar)
        self.trs.append(tr)
        if self.atr is None:
            if len(self.trs) < self.window:
                self.prev_close = bar.close
                return None
            self.atr = sum(self.trs) / self.window
        else:
            self.atr = (self.atr * (self.window - 1) + tr) / self.window
        self.prev_close = bar.close
        return self.atr


@dataclass
class RollingSlope:
    window: int
    values: Deque[float] = None

    def __post_init__(self) -> None:
        self.values = deque(maxlen=self.window)

    def update(self, value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        self.values.append(value)
        if len(self.values) < self.window:
            return None
        return safe_div(self.values[-1] - self.values[0], self.window - 1)


@dataclass
class SessionVWAP:
    """Intraday VWAP that resets on each new session date."""
    _session_key: object = None
    _cumulative_pv: float = 0.0
    _cumulative_vol: float = 0.0
    vwap: Optional[float] = None

    def update(self, bar: Bar, session_key: object) -> Optional[float]:
        if session_key != self._session_key:
            self._session_key = session_key
            self._cumulative_pv = 0.0
            self._cumulative_vol = 0.0
        tp = (bar.high + bar.low + bar.close) / 3.0
        self._cumulative_pv += tp * bar.volume
        self._cumulative_vol += bar.volume
        if self._cumulative_vol > 0:
            self.vwap = self._cumulative_pv / self._cumulative_vol
        return self.vwap
