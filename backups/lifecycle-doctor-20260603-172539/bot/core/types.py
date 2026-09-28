from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any


class Regime(str, Enum):
    BULL = "bull"
    BEAR = "bear"
    NEUTRAL = "neutral"


class NarrowWideState(str, Enum):
    NARROW = "narrow"
    WIDE = "wide"
    UNKNOWN = "unknown"


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


@dataclass
class Signal:
    symbol: str
    side: Side
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class OrderIntent:
    symbol: str
    side: Side
    qty: int
    order_type: OrderType
    limit_price: Optional[float]
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Order:
    symbol: str
    side: Side
    qty: int
    order_type: OrderType
    limit_price: Optional[float]
    timestamp: datetime
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Fill:
    order: Order
    price: float
    timestamp: datetime
    slippage: float
    commission: float


@dataclass
class Position:
    symbol: str
    qty: int
    entry_price: float
    entry_time: datetime
    stop_price: float
    initial_stop: float
    risk_per_share: float
    bars_held: int = 0
    max_favorable_excursion: float = 0.0
    max_adverse_excursion: float = 0.0
    partial_1_taken: bool = False
    partial_2_taken: bool = False
    trail_stop: Optional[float] = None
    trail_breach_count: int = 0


@dataclass
class TradeRecord:
    symbol: str
    entry_time: datetime
    exit_time: datetime
    qty: int
    entry_price: float
    exit_price: float
    pnl: float
    reason: str
    side: Optional[Side] = None
    mfe: float = 0.0
    mae: float = 0.0
    r_multiple: float = 0.0
    bars_held: int = 0


@dataclass
class DecisionTrace:
    symbol: str
    timestamp: datetime
    regime: Regime
    narrow_wide: NarrowWideState
    transition_n2w: bool
    spread: Optional[float]
    atr_percent: Optional[float]
    triggers: Dict[str, Any]
    sizing: Dict[str, Any]
    stops: Dict[str, Any]
    action: str
    reason: str
