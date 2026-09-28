from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, Dict, List, Optional

from .indicators import RollingATR, RollingSMA, RollingSlope
from .types import Bar, OrderType, Signal, Side
from .utils import safe_div


class VelezPlay(str, Enum):
    ELEPHANT = "elephant_bar"
    BULL_180 = "bull_180"
    BEAR_180 = "bear_180"
    BOTTOMING_TAIL = "bottoming_tail"
    TOPPING_TAIL = "topping_tail"


class VelezLocation(str, Enum):
    NEAR_20 = "location_1_near_20_sma"
    EXTENDED_20 = "location_2_extended_from_20_sma"
    NEAR_200 = "location_3_near_200_sma"


@dataclass(frozen=True)
class CandleShape:
    body: float
    range: float
    upper_wick: float
    lower_wick: float
    body_midpoint: float
    bullish: bool
    bearish: bool


@dataclass(frozen=True)
class LocationAssessment:
    locations: List[VelezLocation]
    near_20: bool
    extended_above_20: bool
    extended_below_20: bool
    near_200: bool
    sma20: Optional[float]
    sma200: Optional[float]
    sma20_slope: Optional[float]
    sma200_slope: Optional[float]
    distance_to_sma20_pct: Optional[float]

    @property
    def actionable(self) -> bool:
        return bool(self.locations)


@dataclass
class VelezContext:
    sma20: RollingSMA
    sma200: RollingSMA
    sma20_slope: RollingSlope
    sma200_slope: RollingSlope
    atr: RollingATR
    bars: Deque[Bar]
    bodies: Deque[float]
    volumes: Deque[float]
    prev_sma20: Optional[float] = None
    prev_sma200: Optional[float] = None
    prev_close: Optional[float] = None
    last_location: Optional[LocationAssessment] = None


@dataclass(frozen=True)
class PyramidDecision:
    allowed: bool
    qty: int
    reason: str
    metadata: Dict[str, object] = field(default_factory=dict)


def candle_shape(bar: Bar) -> CandleShape:
    body = abs(bar.close - bar.open)
    bar_range = max(bar.high - bar.low, 0.0)
    upper = max(bar.high - max(bar.open, bar.close), 0.0)
    lower = max(min(bar.open, bar.close) - bar.low, 0.0)
    return CandleShape(
        body=body,
        range=bar_range,
        upper_wick=upper,
        lower_wick=lower,
        body_midpoint=(bar.open + bar.close) / 2.0,
        bullish=bar.close > bar.open,
        bearish=bar.close < bar.open,
    )


class VelezInstitutionalStrategy:
    """Oliver Velez candle-play engine with strict SMA location gating."""

    def __init__(self, config: dict, logger=None) -> None:
        self.config = config
        self.logger = logger
        self.symbols: Dict[str, VelezContext] = {}

    def _get_context(self, symbol: str) -> VelezContext:
        if symbol in self.symbols:
            return self.symbols[symbol]

        cfg = self.config
        history = max(
            cfg.get("sma_slow", 200),
            cfg.get("history_bars", 220),
            cfg.get("elephant", {}).get("body_lookback", 5) + 5,
        )
        ctx = VelezContext(
            sma20=RollingSMA(cfg.get("sma_fast", 20)),
            sma200=RollingSMA(cfg.get("sma_slow", 200)),
            sma20_slope=RollingSlope(cfg.get("slope_lookback", 5)),
            sma200_slope=RollingSlope(cfg.get("slope_lookback", 5)),
            atr=RollingATR(cfg.get("atr_period", 14)),
            bars=deque(maxlen=history),
            bodies=deque(maxlen=history),
            volumes=deque(maxlen=history),
        )
        self.symbols[symbol] = ctx
        return ctx

    def on_bar(self, symbol: str, bar: Bar) -> List[Signal]:
        ctx = self._get_context(symbol)
        shape = candle_shape(bar)

        sma20 = ctx.sma20.update(bar.close)
        sma200 = ctx.sma200.update(bar.close)
        slope20 = ctx.sma20_slope.update(sma20)
        slope200 = ctx.sma200_slope.update(sma200)
        atr = ctx.atr.update(bar)
        location = self._assess_location(bar, sma20, sma200, slope20, slope200, atr)
        ctx.last_location = location

        signals: List[Signal] = []
        signals.extend(self._elephant_bar_signals(symbol, bar, shape, ctx, location, atr))
        signals.extend(self._one_eighty_signals(symbol, bar, shape, ctx, location, atr))
        signals.extend(self._tail_signals(symbol, bar, shape, ctx, location, atr))

        ctx.prev_close = bar.close
        ctx.prev_sma20 = sma20
        ctx.prev_sma200 = sma200
        ctx.bars.append(bar)
        ctx.bodies.append(shape.body)
        ctx.volumes.append(bar.volume)
        return signals

    def indicator_snapshot(self, symbol: str) -> dict:
        ctx = self.symbols.get(symbol)
        if ctx is None:
            return {}
        return {
            "sma_fast": ctx.prev_sma20,
            "sma_slow": ctx.prev_sma200,
            "atr": ctx.atr.atr,
            "location": ctx.last_location,
        }

    def _assess_location(
        self,
        bar: Bar,
        sma20: Optional[float],
        sma200: Optional[float],
        slope20: Optional[float],
        slope200: Optional[float],
        atr: Optional[float],
    ) -> LocationAssessment:
        near_pct = self.config.get("near_sma_pct", 0.0025)
        near_atr_mult = self.config.get("near_sma_atr_mult", 0.35)
        extended_pct = self.config.get("extended_sma_pct", 0.012)
        extended_atr_mult = self.config.get("extended_sma_atr_mult", 1.0)

        def near_sma(sma: Optional[float]) -> bool:
            if sma is None:
                return False
            pct_ok = abs(bar.close - sma) / max(bar.close, 1e-9) <= near_pct
            atr_ok = atr is not None and abs(bar.close - sma) <= near_atr_mult * atr
            touched = bar.low <= sma <= bar.high
            return pct_ok or atr_ok or touched

        near20 = near_sma(sma20)
        near200 = near_sma(sma200)

        extended_above = False
        extended_below = False
        distance_pct: Optional[float] = None
        if sma20 is not None:
            distance = bar.close - sma20
            distance_pct = safe_div(distance, sma20)
            pct_extended = abs(distance_pct) >= extended_pct
            atr_extended = atr is not None and abs(distance) >= extended_atr_mult * atr
            if pct_extended or atr_extended:
                extended_above = distance > 0
                extended_below = distance < 0

        locations: List[VelezLocation] = []
        if near20:
            locations.append(VelezLocation.NEAR_20)
        if extended_above or extended_below:
            locations.append(VelezLocation.EXTENDED_20)
        if near200:
            locations.append(VelezLocation.NEAR_200)

        return LocationAssessment(
            locations=locations,
            near_20=near20,
            extended_above_20=extended_above,
            extended_below_20=extended_below,
            near_200=near200,
            sma20=sma20,
            sma200=sma200,
            sma20_slope=slope20,
            sma200_slope=slope200,
            distance_to_sma20_pct=distance_pct,
        )

    def _elephant_bar_signals(
        self,
        symbol: str,
        bar: Bar,
        shape: CandleShape,
        ctx: VelezContext,
        location: LocationAssessment,
        atr: Optional[float],
    ) -> List[Signal]:
        cfg = self.config.get("elephant", {})
        if not cfg.get("enabled", True) or not location.actionable:
            return []

        lookback = cfg.get("body_lookback", 5)
        if len(ctx.bodies) < lookback or len(ctx.bars) < lookback:
            return []
        avg_body = sum(list(ctx.bodies)[-lookback:]) / lookback
        if avg_body <= 0 or shape.body < cfg.get("min_body_mult", 1.8) * avg_body:
            return []
        if shape.range <= 0:
            return []
        max_each_wick_pct = cfg.get("max_each_wick_pct", 0.2)
        max_total_wick_pct = cfg.get("max_total_wick_pct", 0.35)
        if shape.upper_wick / shape.range > max_each_wick_pct:
            return []
        if shape.lower_wick / shape.range > max_each_wick_pct:
            return []
        if (shape.upper_wick + shape.lower_wick) / shape.range > max_total_wick_pct:
            return []

        prior = list(ctx.bars)[-cfg.get("structure_lookback", 5) :]
        prior_high = max(b.high for b in prior)
        prior_low = min(b.low for b in prior)
        bullish_cross = self._crosses_ma_up(bar, ctx, location)
        bearish_cross = self._crosses_ma_down(bar, ctx, location)

        if shape.bullish and (bar.close > prior_high or bullish_cross):
            return [
                self._build_signal(
                    symbol=symbol,
                    side=Side.BUY,
                    play=VelezPlay.ELEPHANT,
                    bar=bar,
                    shape=shape,
                    location=location,
                    stop_price=self._stop_below(symbol, bar.low),
                    trigger_price=prior_high,
                    force_limit=self._is_climactic(shape, avg_body, atr, cfg),
                    metadata={
                        "avg_body": avg_body,
                        "prior_high": prior_high,
                        "prior_low": prior_low,
                        "atr": atr,
                    },
                )
            ]

        if shape.bearish and (bar.close < prior_low or bearish_cross):
            return [
                self._build_signal(
                    symbol=symbol,
                    side=Side.SELL,
                    play=VelezPlay.ELEPHANT,
                    bar=bar,
                    shape=shape,
                    location=location,
                    stop_price=self._stop_above(symbol, bar.high),
                    trigger_price=prior_low,
                    force_limit=self._is_climactic(shape, avg_body, atr, cfg),
                    metadata={
                        "avg_body": avg_body,
                        "prior_high": prior_high,
                        "prior_low": prior_low,
                        "atr": atr,
                    },
                )
            ]

        return []

    def _one_eighty_signals(
        self,
        symbol: str,
        bar: Bar,
        shape: CandleShape,
        ctx: VelezContext,
        location: LocationAssessment,
        atr: Optional[float],
    ) -> List[Signal]:
        cfg = self.config.get("one_eighty", {})
        if not cfg.get("enabled", True) or len(ctx.bars) < 1:
            return []
        if not (location.near_20 or location.near_200):
            return []

        prev = ctx.bars[-1]
        prev_shape = candle_shape(prev)
        if prev_shape.body <= 0 or shape.body <= 0:
            return []

        recover_pct = cfg.get("recover_pct", 0.8)
        sequence_low = min(prev.low, bar.low)
        sequence_high = max(prev.high, bar.high)

        if prev_shape.bearish and shape.bullish:
            recovery_mark = prev.close + (prev.open - prev.close) * recover_pct
            if bar.close >= recovery_mark and self._bullish_ma_context(location):
                return [
                    self._build_signal(
                        symbol=symbol,
                        side=Side.BUY,
                        play=VelezPlay.BULL_180,
                        bar=bar,
                        shape=shape,
                        location=location,
                        stop_price=self._stop_below(symbol, sequence_low),
                        trigger_price=recovery_mark,
                        metadata={
                            "bar1_open": prev.open,
                            "bar1_close": prev.close,
                            "recovery_mark": recovery_mark,
                            "atr": atr,
                        },
                    )
                ]

        if prev_shape.bullish and shape.bearish:
            recovery_mark = prev.close - (prev.close - prev.open) * recover_pct
            if bar.close <= recovery_mark and self._bearish_ma_context(location):
                return [
                    self._build_signal(
                        symbol=symbol,
                        side=Side.SELL,
                        play=VelezPlay.BEAR_180,
                        bar=bar,
                        shape=shape,
                        location=location,
                        stop_price=self._stop_above(symbol, sequence_high),
                        trigger_price=recovery_mark,
                        metadata={
                            "bar1_open": prev.open,
                            "bar1_close": prev.close,
                            "recovery_mark": recovery_mark,
                            "atr": atr,
                        },
                    )
                ]

        return []

    def _tail_signals(
        self,
        symbol: str,
        bar: Bar,
        shape: CandleShape,
        ctx: VelezContext,
        location: LocationAssessment,
        atr: Optional[float],
    ) -> List[Signal]:
        cfg = self.config.get("tail", {})
        if not cfg.get("enabled", True) or shape.range <= 0:
            return []

        tail_pct = cfg.get("min_tail_pct", 0.66)
        declined = self._multi_bar_decline(ctx, cfg.get("trend_bars", 3))
        rallied = self._multi_bar_rally(ctx, cfg.get("trend_bars", 3))

        if shape.lower_wick / shape.range >= tail_pct:
            valid_location = (declined and location.extended_below_20) or (
                location.near_200 and self._slope_is_rising(location.sma200_slope)
            )
            if valid_location:
                limit_price = bar.low + shape.lower_wick * 0.5
                return [
                    self._build_signal(
                        symbol=symbol,
                        side=Side.BUY,
                        play=VelezPlay.BOTTOMING_TAIL,
                        bar=bar,
                        shape=shape,
                        location=location,
                        stop_price=self._stop_below(symbol, bar.low),
                        trigger_price=bar.close,
                        force_limit=cfg.get("prefer_tail_limit", True),
                        limit_price=limit_price,
                        metadata={"tail_pct": shape.lower_wick / shape.range, "atr": atr},
                    )
                ]

        if shape.upper_wick / shape.range >= tail_pct:
            valid_location = (rallied and location.extended_above_20) or (
                location.near_200 and self._slope_is_declining(location.sma200_slope)
            )
            if valid_location:
                limit_price = bar.high - shape.upper_wick * 0.5
                return [
                    self._build_signal(
                        symbol=symbol,
                        side=Side.SELL,
                        play=VelezPlay.TOPPING_TAIL,
                        bar=bar,
                        shape=shape,
                        location=location,
                        stop_price=self._stop_above(symbol, bar.high),
                        trigger_price=bar.close,
                        force_limit=cfg.get("prefer_tail_limit", True),
                        limit_price=limit_price,
                        metadata={"tail_pct": shape.upper_wick / shape.range, "atr": atr},
                    )
                ]

        return []

    def _build_signal(
        self,
        *,
        symbol: str,
        side: Side,
        play: VelezPlay,
        bar: Bar,
        shape: CandleShape,
        location: LocationAssessment,
        stop_price: float,
        trigger_price: float,
        force_limit: bool = False,
        limit_price: Optional[float] = None,
        metadata: Optional[dict] = None,
    ) -> Signal:
        order_type = OrderType.MARKET
        selected_limit = limit_price
        no_chase_pct = self.config.get("entry", {}).get("no_chase_body_pct", 0.05)
        chase_distance = abs(bar.close - trigger_price)
        chased = shape.body > 0 and chase_distance > (no_chase_pct * shape.body)
        if force_limit or chased:
            order_type = OrderType.LIMIT
            if selected_limit is None:
                selected_limit = shape.body_midpoint

        payload = {
            "play": play.value,
            "entry_price": bar.close if order_type == OrderType.MARKET else selected_limit,
            "stop_price": stop_price,
            "trigger_price": trigger_price,
            "order_type": order_type.value,
            "limit_price": selected_limit,
            "chased": chased,
            "location": [loc.value for loc in location.locations],
            "sma20": location.sma20,
            "sma200": location.sma200,
            "sma20_slope": location.sma20_slope,
            "sma200_slope": location.sma200_slope,
            "distance_to_sma20_pct": location.distance_to_sma20_pct,
            "close": bar.close,
            "timestamp": bar.timestamp,
        }
        if metadata:
            payload.update(metadata)

        return Signal(
            symbol=symbol,
            side=side,
            reason=play.value,
            metadata=payload,
        )

    def _crosses_ma_up(self, bar: Bar, ctx: VelezContext, location: LocationAssessment) -> bool:
        if ctx.prev_close is None:
            return False
        crossed20 = (
            ctx.prev_sma20 is not None
            and ctx.prev_close <= ctx.prev_sma20
            and bar.close > ctx.prev_sma20
            and self._slope_is_flat_or_rising(location.sma20_slope)
        )
        crossed200 = (
            ctx.prev_sma200 is not None
            and ctx.prev_close <= ctx.prev_sma200
            and bar.close > ctx.prev_sma200
            and self._slope_is_flat_or_rising(location.sma200_slope)
        )
        return crossed20 or crossed200

    def _crosses_ma_down(self, bar: Bar, ctx: VelezContext, location: LocationAssessment) -> bool:
        if ctx.prev_close is None:
            return False
        crossed20 = (
            ctx.prev_sma20 is not None
            and ctx.prev_close >= ctx.prev_sma20
            and bar.close < ctx.prev_sma20
            and self._slope_is_flat_or_declining(location.sma20_slope)
        )
        crossed200 = (
            ctx.prev_sma200 is not None
            and ctx.prev_close >= ctx.prev_sma200
            and bar.close < ctx.prev_sma200
            and self._slope_is_flat_or_declining(location.sma200_slope)
        )
        return crossed20 or crossed200

    def _is_climactic(self, shape: CandleShape, avg_body: float, atr: Optional[float], cfg: dict) -> bool:
        if avg_body > 0 and shape.body >= cfg.get("climactic_body_mult", 3.0) * avg_body:
            return True
        return atr is not None and shape.range >= cfg.get("climactic_atr_mult", 2.2) * atr

    def _bullish_ma_context(self, location: LocationAssessment) -> bool:
        if location.near_20 and self._slope_is_flat_or_rising(location.sma20_slope):
            return True
        return location.near_200 and self._slope_is_flat_or_rising(location.sma200_slope)

    def _bearish_ma_context(self, location: LocationAssessment) -> bool:
        if location.near_20 and self._slope_is_flat_or_declining(location.sma20_slope):
            return True
        return location.near_200 and self._slope_is_flat_or_declining(location.sma200_slope)

    def _slope_tolerance(self) -> float:
        return self.config.get("slope_tolerance", 1e-9)

    def _slope_is_rising(self, slope: Optional[float]) -> bool:
        return slope is not None and slope > self._slope_tolerance()

    def _slope_is_declining(self, slope: Optional[float]) -> bool:
        return slope is not None and slope < -self._slope_tolerance()

    def _slope_is_flat_or_rising(self, slope: Optional[float]) -> bool:
        return slope is None or slope >= -self._slope_tolerance()

    def _slope_is_flat_or_declining(self, slope: Optional[float]) -> bool:
        return slope is None or slope <= self._slope_tolerance()

    def _multi_bar_decline(self, ctx: VelezContext, count: int) -> bool:
        if len(ctx.bars) < count:
            return False
        bars = list(ctx.bars)[-count:]
        return all(bars[i].close < bars[i - 1].close for i in range(1, len(bars)))

    def _multi_bar_rally(self, ctx: VelezContext, count: int) -> bool:
        if len(ctx.bars) < count:
            return False
        bars = list(ctx.bars)[-count:]
        return all(bars[i].close > bars[i - 1].close for i in range(1, len(bars)))

    def _tick_size(self, symbol: str) -> float:
        tick_cfg = self.config.get("tick_size", {})
        if isinstance(tick_cfg, dict):
            return float(tick_cfg.get(symbol, tick_cfg.get("default", 0.01)))
        return float(tick_cfg or 0.01)

    def _stop_below(self, symbol: str, price: float) -> float:
        return self._round_to_tick(symbol, price - self._tick_size(symbol))

    def _stop_above(self, symbol: str, price: float) -> float:
        return self._round_to_tick(symbol, price + self._tick_size(symbol))

    def _round_to_tick(self, symbol: str, price: float) -> float:
        tick = self._tick_size(symbol)
        if tick <= 0:
            return price
        rounded = round(price / tick) * tick
        decimals = max(0, len(f"{tick:.10f}".rstrip("0").split(".")[-1]))
        return round(rounded, decimals)


def calculate_core_position_size(
    *,
    max_dollar_risk: float,
    entry_price: float,
    stop_price: float,
    contract_multiplier: float = 1.0,
    max_order_qty: int = 1000000,
) -> int:
    risk_per_unit = abs(entry_price - stop_price) * contract_multiplier
    if max_dollar_risk <= 0 or risk_per_unit <= 0:
        return 0
    return max(0, min(int(max_dollar_risk / risk_per_unit), max_order_qty))


def calculate_pyramid_add_qty(current_qty: int, max_core_qty: Optional[int] = None) -> int:
    add_qty = int(abs(current_qty) * 0.5)
    if max_core_qty is not None:
        add_qty = min(add_qty, max(0, max_core_qty - abs(current_qty)))
    return max(0, add_qty)


def evaluate_pyramid_add(
    *,
    current_qty: int,
    entry_price: float,
    stop_price: float,
    current_price: float,
    current_volume: float,
    recent_volumes: List[float],
    max_core_qty: Optional[int] = None,
) -> PyramidDecision:
    if current_qty == 0:
        return PyramidDecision(False, 0, "no_position")

    long_position = current_qty > 0
    profitable = current_price > entry_price if long_position else current_price < entry_price
    if not profitable:
        return PyramidDecision(False, 0, "position_not_profitable")

    risk_mitigated = stop_price >= entry_price if long_position else stop_price <= entry_price
    if not risk_mitigated:
        return PyramidDecision(False, 0, "initial_risk_not_mitigated")

    volume_ok = True
    avg_recent_volume = None
    if recent_volumes:
        avg_recent_volume = sum(recent_volumes) / len(recent_volumes)
        volume_ok = current_volume < avg_recent_volume
    if not volume_ok:
        return PyramidDecision(
            False,
            0,
            "opposing_or_pullback_volume_not_diminishing",
            {"avg_recent_volume": avg_recent_volume},
        )

    qty = calculate_pyramid_add_qty(current_qty, max_core_qty)
    if qty <= 0:
        return PyramidDecision(False, 0, "max_core_capacity_reached")
    return PyramidDecision(True, qty, "ok", {"avg_recent_volume": avg_recent_volume})
