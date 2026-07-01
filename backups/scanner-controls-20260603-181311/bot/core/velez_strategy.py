from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Deque, Dict, List, Optional

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - keeps the strategy portable if zoneinfo is unavailable.
    ZoneInfo = None

from .indicators import RollingATR, RollingSMA, RollingSlope
from .types import Bar, OrderType, Signal, Side
from .utils import safe_div


class VelezPlay(str, Enum):
    ELEPHANT = "elephant_bar"
    BULL_180 = "bull_180"
    BEAR_180 = "bear_180"
    BOTTOMING_TAIL = "bottoming_tail"
    TOPPING_TAIL = "topping_tail"
    BUY_SETUP = "velez_buy_setup"
    SELL_SETUP = "velez_sell_setup"
    NRB_ACORN = "nrb_acorn"
    COLOR_CHANGE_ADD = "color_change_add"
    FAB4_TRAP_BREAKOUT = "fab4_trap_breakout"
    FAILED_NEW_HIGH = "failed_new_high"
    FAILED_NEW_LOW = "failed_new_low"
    OPENING_GAP_GO = "opening_gap_go"
    OPENING_GAP_FADE = "opening_gap_fade"
    TIME_SPACE_BREAKOUT = "time_space_breakout"


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
class OpeningGapState:
    session_date: Optional[object] = None
    prior_close: Optional[float] = None
    first_open: Optional[float] = None
    first_high: Optional[float] = None
    first_low: Optional[float] = None
    first_close: Optional[float] = None
    gap_direction: Optional[str] = None
    gap_pct: Optional[float] = None
    bars_seen: int = 0
    last_minutes_since_open: Optional[int] = None
    go_used: bool = False
    fade_used: bool = False
    breakout_used: bool = False


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
    color_add_used: Dict[str, bool] = field(default_factory=lambda: {"buy": False, "sell": False})
    opening_gap: OpeningGapState = field(default_factory=OpeningGapState)


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
        self._update_opening_gap_state(ctx, bar)

        signals: List[Signal] = []
        signals.extend(self._opening_gap_signals(symbol, bar, shape, ctx, location, atr))
        signals.extend(self._time_space_breakout_signals(symbol, bar, shape, ctx, location, atr))
        signals.extend(self._elephant_bar_signals(symbol, bar, shape, ctx, location, atr))
        signals.extend(self._one_eighty_signals(symbol, bar, shape, ctx, location, atr))
        signals.extend(self._tail_signals(symbol, bar, shape, ctx, location, atr))
        signals.extend(self._failed_breakout_signals(symbol, bar, shape, ctx, location, atr))
        signals.extend(self._color_change_add_signals(symbol, bar, shape, ctx, location, atr))
        signals.extend(self._buy_sell_setup_signals(symbol, bar, shape, ctx, location, atr))
        signals.extend(self._nrb_acorn_signals(symbol, bar, shape, ctx, location, atr))
        signals.extend(self._fab4_trap_signals(symbol, bar, shape, ctx, location, atr))
        signals = self._prioritized_signals(signals)

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

    def _opening_gap_signals(
        self,
        symbol: str,
        bar: Bar,
        shape: CandleShape,
        ctx: VelezContext,
        location: LocationAssessment,
        atr: Optional[float],
    ) -> List[Signal]:
        cfg = self.config.get("opening_gap", {})
        if not cfg.get("enabled", True) or not location.actionable:
            return []

        state = ctx.opening_gap
        if not self._opening_state_ready(state):
            return []
        if state.last_minutes_since_open is None or state.last_minutes_since_open > cfg.get("opening_window_minutes", 15):
            return []
        if state.bars_seen > cfg.get("max_signal_bars", 3):
            return []
        gap_pct = float(state.gap_pct or 0.0)
        if abs(gap_pct) < cfg.get("min_gap_pct", 0.003):
            return []
        if abs(gap_pct) > cfg.get("max_gap_pct", 0.08):
            return []

        first_range = max(float(state.first_high or 0.0) - float(state.first_low or 0.0), 0.0)
        if first_range <= 0:
            return []
        close_pos = safe_div(bar.close - float(state.first_low), first_range)
        close_weak_pos = safe_div(float(state.first_high) - bar.close, first_range)
        upper_rejection = safe_div(shape.upper_wick, shape.range)
        lower_rejection = safe_div(shape.lower_wick, shape.range)
        min_close_pos = cfg.get("first_bar_close_position_pct", 0.65)
        rejection_pct = cfg.get("fade_rejection_wick_pct", 0.35)
        gap_fill_space_pct = cfg.get("min_gap_fill_space_pct", 0.002)

        signals: List[Signal] = []
        gap_up = gap_pct > 0
        go_metrics = self._time_space_metrics(ctx, bar, state, location, atr, Side.BUY if gap_up else Side.SELL, cfg)
        if not state.go_used and go_metrics["clean_space"] and go_metrics["score"] >= cfg.get("min_time_space_score", 0.65):
            if gap_up:
                first_bar_control = state.bars_seen == 1 and shape.bullish and close_pos >= min_close_pos
                opening_range_break = state.bars_seen > 1 and shape.bullish and bar.close > float(state.first_high)
                if first_bar_control or opening_range_break:
                    state.go_used = True
                    signals.append(
                        self._build_signal(
                            symbol=symbol,
                            side=Side.BUY,
                            play=VelezPlay.OPENING_GAP_GO,
                            bar=bar,
                            shape=shape,
                            location=location,
                            stop_price=self._stop_below(symbol, min(float(state.first_low), bar.low)),
                            trigger_price=float(state.first_high),
                            metadata=self._opening_metadata("gap_and_go", state, go_metrics, atr),
                        )
                    )
            else:
                first_bar_control = state.bars_seen == 1 and shape.bearish and close_weak_pos >= min_close_pos
                opening_range_break = state.bars_seen > 1 and shape.bearish and bar.close < float(state.first_low)
                if first_bar_control or opening_range_break:
                    state.go_used = True
                    signals.append(
                        self._build_signal(
                            symbol=symbol,
                            side=Side.SELL,
                            play=VelezPlay.OPENING_GAP_GO,
                            bar=bar,
                            shape=shape,
                            location=location,
                            stop_price=self._stop_above(symbol, max(float(state.first_high), bar.high)),
                            trigger_price=float(state.first_low),
                            metadata=self._opening_metadata("gap_and_go", state, go_metrics, atr),
                        )
                    )
        if signals:
            return signals

        if state.fade_used:
            return []

        if gap_up:
            fill_space = safe_div(bar.close - float(state.prior_close), bar.close)
            fade_context = location.extended_above_20 or location.near_200 or not go_metrics["clean_space"]
            fade_trigger = shape.bearish and (bar.close < float(state.first_open) or upper_rejection >= rejection_pct or close_weak_pos >= min_close_pos)
            if fade_context and fade_trigger and fill_space >= gap_fill_space_pct:
                state.fade_used = True
                metrics = self._time_space_metrics(ctx, bar, state, location, atr, Side.SELL, cfg)
                signals.append(
                    self._build_signal(
                        symbol=symbol,
                        side=Side.SELL,
                        play=VelezPlay.OPENING_GAP_FADE,
                        bar=bar,
                        shape=shape,
                        location=location,
                        stop_price=self._stop_above(symbol, max(float(state.first_high), bar.high)),
                        trigger_price=float(state.first_open),
                        metadata=self._opening_metadata("gap_fade_to_prior_close", state, metrics, atr),
                    )
                )
        else:
            fill_space = safe_div(float(state.prior_close) - bar.close, bar.close)
            fade_context = location.extended_below_20 or location.near_200 or not go_metrics["clean_space"]
            fade_trigger = shape.bullish and (bar.close > float(state.first_open) or lower_rejection >= rejection_pct or close_pos >= min_close_pos)
            if fade_context and fade_trigger and fill_space >= gap_fill_space_pct:
                state.fade_used = True
                metrics = self._time_space_metrics(ctx, bar, state, location, atr, Side.BUY, cfg)
                signals.append(
                    self._build_signal(
                        symbol=symbol,
                        side=Side.BUY,
                        play=VelezPlay.OPENING_GAP_FADE,
                        bar=bar,
                        shape=shape,
                        location=location,
                        stop_price=self._stop_below(symbol, min(float(state.first_low), bar.low)),
                        trigger_price=float(state.first_open),
                        metadata=self._opening_metadata("gap_fade_to_prior_close", state, metrics, atr),
                    )
                )

        return signals

    def _time_space_breakout_signals(
        self,
        symbol: str,
        bar: Bar,
        shape: CandleShape,
        ctx: VelezContext,
        location: LocationAssessment,
        atr: Optional[float],
    ) -> List[Signal]:
        cfg = self.config.get("time_space", {})
        if not cfg.get("enabled", True) or not (location.near_20 or location.near_200):
            return []
        state = ctx.opening_gap
        if not self._opening_state_ready(state):
            return []
        if state.breakout_used:
            return []
        if state.bars_seen < cfg.get("min_bars_after_open", 2) or state.bars_seen > cfg.get("max_signal_bars", 6):
            return []
        if state.last_minutes_since_open is None or state.last_minutes_since_open > cfg.get("opening_window_minutes", 30):
            return []
        if abs(float(state.gap_pct or 0.0)) >= cfg.get("max_neutral_gap_pct", 0.003):
            return []

        if shape.bullish and bar.close > float(state.first_high) and self._bullish_ma_context(location):
            metrics = self._time_space_metrics(ctx, bar, state, location, atr, Side.BUY, cfg)
            if metrics["clean_space"] and metrics["score"] >= cfg.get("min_time_space_score", 0.65):
                state.breakout_used = True
                return [
                    self._build_signal(
                        symbol=symbol,
                        side=Side.BUY,
                        play=VelezPlay.TIME_SPACE_BREAKOUT,
                        bar=bar,
                        shape=shape,
                        location=location,
                        stop_price=self._stop_below(symbol, min(float(state.first_low), bar.low)),
                        trigger_price=float(state.first_high),
                        metadata=self._opening_metadata("opening_range_time_space_breakout", state, metrics, atr),
                    )
                ]

        if shape.bearish and bar.close < float(state.first_low) and self._bearish_ma_context(location):
            metrics = self._time_space_metrics(ctx, bar, state, location, atr, Side.SELL, cfg)
            if metrics["clean_space"] and metrics["score"] >= cfg.get("min_time_space_score", 0.65):
                state.breakout_used = True
                return [
                    self._build_signal(
                        symbol=symbol,
                        side=Side.SELL,
                        play=VelezPlay.TIME_SPACE_BREAKOUT,
                        bar=bar,
                        shape=shape,
                        location=location,
                        stop_price=self._stop_above(symbol, max(float(state.first_high), bar.high)),
                        trigger_price=float(state.first_low),
                        metadata=self._opening_metadata("opening_range_time_space_breakout", state, metrics, atr),
                    )
                ]
        return []

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
                        "body_mult": safe_div(shape.body, avg_body),
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
                        "body_mult": safe_div(shape.body, avg_body),
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
            actual_recovery = safe_div(bar.close - prev.close, prev.open - prev.close)
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
                            "recovery_pct": actual_recovery,
                            "atr": atr,
                        },
                    )
                ]

        if prev_shape.bullish and shape.bearish:
            recovery_mark = prev.close - (prev.close - prev.open) * recover_pct
            actual_recovery = safe_div(prev.close - bar.close, prev.close - prev.open)
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
                            "recovery_pct": actual_recovery,
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

    def _buy_sell_setup_signals(
        self,
        symbol: str,
        bar: Bar,
        shape: CandleShape,
        ctx: VelezContext,
        location: LocationAssessment,
        atr: Optional[float],
    ) -> List[Signal]:
        cfg = self.config.get("buy_sell_setup", {})
        if not cfg.get("enabled", True) or len(ctx.bars) < cfg.get("pullback_bars", 2):
            return []
        if shape.body <= 0 or not (location.near_20 or location.near_200):
            return []

        lookback = cfg.get("pullback_bars", 2)
        recent = list(ctx.bars)[-lookback:]
        prior_high = max(item.high for item in recent)
        prior_low = min(item.low for item in recent)
        pulled_back = self._recent_pullback(recent)
        pushed_up = self._recent_pushup(recent)

        if (
            self._bull_trend(location)
            and pulled_back
            and shape.bullish
            and (bar.close > prior_high or (location.sma20 is not None and bar.close > location.sma20))
        ):
            return [
                self._build_signal(
                    symbol=symbol,
                    side=Side.BUY,
                    play=VelezPlay.BUY_SETUP,
                    bar=bar,
                    shape=shape,
                    location=location,
                    stop_price=self._stop_below(symbol, min(prior_low, bar.low)),
                    trigger_price=prior_high,
                    metadata={
                        "pullback_bars": lookback,
                        "prior_high": prior_high,
                        "prior_low": prior_low,
                        "atr": atr,
                    },
                )
            ]

        if (
            self._bear_trend(location)
            and pushed_up
            and shape.bearish
            and (bar.close < prior_low or (location.sma20 is not None and bar.close < location.sma20))
        ):
            return [
                self._build_signal(
                    symbol=symbol,
                    side=Side.SELL,
                    play=VelezPlay.SELL_SETUP,
                    bar=bar,
                    shape=shape,
                    location=location,
                    stop_price=self._stop_above(symbol, max(prior_high, bar.high)),
                    trigger_price=prior_low,
                    metadata={
                        "pullback_bars": lookback,
                        "prior_high": prior_high,
                        "prior_low": prior_low,
                        "atr": atr,
                    },
                )
            ]
        return []

    def _nrb_acorn_signals(
        self,
        symbol: str,
        bar: Bar,
        shape: CandleShape,
        ctx: VelezContext,
        location: LocationAssessment,
        atr: Optional[float],
    ) -> List[Signal]:
        cfg = self.config.get("nrb_acorn", {})
        lookback = cfg.get("range_lookback", 7)
        if not cfg.get("enabled", True) or not location.actionable or len(ctx.bars) < max(2, lookback):
            return []

        prev = ctx.bars[-1]
        prev_range = max(prev.high - prev.low, 0.0)
        ranges = [max(item.high - item.low, 0.0) for item in list(ctx.bars)[-lookback:]]
        avg_range = sum(ranges) / len(ranges) if ranges else 0.0
        range_ok = avg_range > 0 and prev_range <= cfg.get("max_range_mult", 0.65) * avg_range
        atr_ok = atr is not None and prev_range <= cfg.get("max_atr_mult", 0.55) * atr
        if not (range_ok or atr_ok):
            return []

        if self._bull_trend(location) and bar.close > prev.high and shape.bullish:
            return [
                self._build_signal(
                    symbol=symbol,
                    side=Side.BUY,
                    play=VelezPlay.NRB_ACORN,
                    bar=bar,
                    shape=shape,
                    location=location,
                    stop_price=self._stop_below(symbol, prev.low),
                    trigger_price=prev.high,
                    metadata={"nrb_range": prev_range, "avg_range": avg_range, "atr": atr},
                )
            ]
        if self._bear_trend(location) and bar.close < prev.low and shape.bearish:
            return [
                self._build_signal(
                    symbol=symbol,
                    side=Side.SELL,
                    play=VelezPlay.NRB_ACORN,
                    bar=bar,
                    shape=shape,
                    location=location,
                    stop_price=self._stop_above(symbol, prev.high),
                    trigger_price=prev.low,
                    metadata={"nrb_range": prev_range, "avg_range": avg_range, "atr": atr},
                )
            ]
        return []

    def _color_change_add_signals(
        self,
        symbol: str,
        bar: Bar,
        shape: CandleShape,
        ctx: VelezContext,
        location: LocationAssessment,
        atr: Optional[float],
    ) -> List[Signal]:
        cfg = self.config.get("color_change", {})
        if not cfg.get("enabled", True) or len(ctx.bars) < 1:
            return []
        prev = ctx.bars[-1]
        prev_shape = candle_shape(prev)
        if prev_shape.body <= 0 or shape.body <= 0:
            return []

        if not self._bull_trend(location):
            ctx.color_add_used["buy"] = False
        if not self._bear_trend(location):
            ctx.color_add_used["sell"] = False

        if (
            not ctx.color_add_used.get("buy", False)
            and self._bull_trend(location)
            and (location.near_20 or location.near_200)
            and prev_shape.bearish
            and shape.bullish
            and bar.close > prev.high
        ):
            ctx.color_add_used["buy"] = True
            return [
                self._build_signal(
                    symbol=symbol,
                    side=Side.BUY,
                    play=VelezPlay.COLOR_CHANGE_ADD,
                    bar=bar,
                    shape=shape,
                    location=location,
                    stop_price=self._stop_below(symbol, min(prev.low, bar.low)),
                    trigger_price=prev.high,
                    metadata=self._color_add_metadata("buy", atr),
                )
            ]

        if (
            not ctx.color_add_used.get("sell", False)
            and self._bear_trend(location)
            and (location.near_20 or location.near_200)
            and prev_shape.bullish
            and shape.bearish
            and bar.close < prev.low
        ):
            ctx.color_add_used["sell"] = True
            return [
                self._build_signal(
                    symbol=symbol,
                    side=Side.SELL,
                    play=VelezPlay.COLOR_CHANGE_ADD,
                    bar=bar,
                    shape=shape,
                    location=location,
                    stop_price=self._stop_above(symbol, max(prev.high, bar.high)),
                    trigger_price=prev.low,
                    metadata=self._color_add_metadata("sell", atr),
                )
            ]
        return []

    def _fab4_trap_signals(
        self,
        symbol: str,
        bar: Bar,
        shape: CandleShape,
        ctx: VelezContext,
        location: LocationAssessment,
        atr: Optional[float],
    ) -> List[Signal]:
        cfg = self.config.get("fab4", {})
        lookback = cfg.get("breakout_lookback", 5)
        if not cfg.get("enabled", True) or not location.actionable or len(ctx.bars) < lookback:
            return []
        if location.sma20 is None or location.sma200 is None:
            return []

        sma_spread_pct = abs(location.sma20 - location.sma200) / max(bar.close, 1e-9)
        compressed_sma = sma_spread_pct <= cfg.get("max_sma_spread_pct", 0.006)
        compressed_atr = atr is not None and abs(location.sma20 - location.sma200) <= cfg.get("max_sma_spread_atr_mult", 0.65) * atr
        if not (compressed_sma or compressed_atr):
            return []

        recent = list(ctx.bars)[-lookback:]
        prior_high = max(item.high for item in recent)
        prior_low = min(item.low for item in recent)
        zone_range = prior_high - prior_low
        range_ok = atr is None or zone_range <= cfg.get("max_zone_atr_mult", 3.0) * atr
        if not range_ok:
            return []

        if shape.bullish and bar.close > prior_high and self._slope_is_flat_or_rising(location.sma20_slope):
            return [
                self._build_signal(
                    symbol=symbol,
                    side=Side.BUY,
                    play=VelezPlay.FAB4_TRAP_BREAKOUT,
                    bar=bar,
                    shape=shape,
                    location=location,
                    stop_price=self._stop_below(symbol, prior_low),
                    trigger_price=prior_high,
                    metadata={
                        "sma_spread_pct": sma_spread_pct,
                        "zone_range": zone_range,
                        "atr": atr,
                    },
                )
            ]
        if shape.bearish and bar.close < prior_low and self._slope_is_flat_or_declining(location.sma20_slope):
            return [
                self._build_signal(
                    symbol=symbol,
                    side=Side.SELL,
                    play=VelezPlay.FAB4_TRAP_BREAKOUT,
                    bar=bar,
                    shape=shape,
                    location=location,
                    stop_price=self._stop_above(symbol, prior_high),
                    trigger_price=prior_low,
                    metadata={
                        "sma_spread_pct": sma_spread_pct,
                        "zone_range": zone_range,
                        "atr": atr,
                    },
                )
            ]
        return []

    def _failed_breakout_signals(
        self,
        symbol: str,
        bar: Bar,
        shape: CandleShape,
        ctx: VelezContext,
        location: LocationAssessment,
        atr: Optional[float],
    ) -> List[Signal]:
        cfg = self.config.get("failed_breakout", {})
        lookback = cfg.get("structure_lookback", 10)
        if not cfg.get("enabled", True) or len(ctx.bars) < lookback or shape.range <= 0:
            return []

        recent = list(ctx.bars)[-lookback:]
        prior_high = max(item.high for item in recent)
        prior_low = min(item.low for item in recent)
        upper_rejection = shape.upper_wick / shape.range >= cfg.get("min_rejection_wick_pct", 0.35)
        lower_rejection = shape.lower_wick / shape.range >= cfg.get("min_rejection_wick_pct", 0.35)

        high_extended = (
            location.sma20 is not None
            and (bar.high - location.sma20) / max(location.sma20, 1e-9) >= self.config.get("extended_sma_pct", 0.012)
        )
        failed_high_context = high_extended or location.extended_above_20 or (location.near_200 and self._slope_is_flat_or_declining(location.sma200_slope))
        if bar.high > prior_high and bar.close < prior_high and (shape.bearish or upper_rejection) and failed_high_context:
            return [
                self._build_signal(
                    symbol=symbol,
                    side=Side.SELL,
                    play=VelezPlay.FAILED_NEW_HIGH,
                    bar=bar,
                    shape=shape,
                    location=location,
                    stop_price=self._stop_above(symbol, bar.high),
                    trigger_price=prior_high,
                    metadata={
                        "prior_high": prior_high,
                        "failed_breakout": "new_high",
                        "rejection_wick_pct": shape.upper_wick / shape.range,
                        "atr": atr,
                    },
                )
            ]

        low_extended = (
            location.sma20 is not None
            and (location.sma20 - bar.low) / max(location.sma20, 1e-9) >= self.config.get("extended_sma_pct", 0.012)
        )
        failed_low_context = low_extended or location.extended_below_20 or (location.near_200 and self._slope_is_flat_or_rising(location.sma200_slope))
        if bar.low < prior_low and bar.close > prior_low and (shape.bullish or lower_rejection) and failed_low_context:
            return [
                self._build_signal(
                    symbol=symbol,
                    side=Side.BUY,
                    play=VelezPlay.FAILED_NEW_LOW,
                    bar=bar,
                    shape=shape,
                    location=location,
                    stop_price=self._stop_below(symbol, bar.low),
                    trigger_price=prior_low,
                    metadata={
                        "prior_low": prior_low,
                        "failed_breakout": "new_low",
                        "rejection_wick_pct": shape.lower_wick / shape.range,
                        "atr": atr,
                    },
                )
            ]
        return []

    def _update_opening_gap_state(self, ctx: VelezContext, bar: Bar) -> OpeningGapState:
        state = ctx.opening_gap
        local_dt = self._local_timestamp(bar.timestamp)
        session_date = local_dt.date()
        if state.session_date != session_date:
            prior_close = ctx.prev_close
            if prior_close is None and ctx.bars:
                prior_close = ctx.bars[-1].close
            ctx.opening_gap = OpeningGapState(session_date=session_date, prior_close=prior_close)
            state = ctx.opening_gap

        minutes_since_open = self._minutes_since_open(local_dt)
        if minutes_since_open < 0:
            return state

        window = max(
            int(self.config.get("opening_gap", {}).get("opening_window_minutes", 15)),
            int(self.config.get("time_space", {}).get("opening_window_minutes", 30)),
        )
        if minutes_since_open > window:
            return state

        if state.bars_seen == 0:
            state.first_open = bar.open
            state.first_high = bar.high
            state.first_low = bar.low
            state.first_close = bar.close
        state.bars_seen += 1
        state.last_minutes_since_open = minutes_since_open

        if state.prior_close:
            state.gap_pct = safe_div(float(state.first_open or bar.open) - float(state.prior_close), float(state.prior_close))
            if state.gap_pct > 0:
                state.gap_direction = "up"
            elif state.gap_pct < 0:
                state.gap_direction = "down"
            else:
                state.gap_direction = "flat"
        return state

    def _opening_state_ready(self, state: OpeningGapState) -> bool:
        return all(
            value is not None
            for value in (
                state.prior_close,
                state.first_open,
                state.first_high,
                state.first_low,
                state.first_close,
                state.gap_pct,
            )
        )

    def _time_space_metrics(
        self,
        ctx: VelezContext,
        bar: Bar,
        state: OpeningGapState,
        location: LocationAssessment,
        atr: Optional[float],
        side: Side,
        cfg: dict,
    ) -> dict:
        prior_bars = self._prior_session_bars(ctx, state.session_date, cfg.get("structure_lookback", 30))
        prior_high = max((item.high for item in prior_bars), default=None)
        prior_low = min((item.low for item in prior_bars), default=None)
        min_space_pct = cfg.get("min_clean_space_pct", 0.004)
        breakout_bonus_pct = cfg.get("breakout_space_bonus_pct", min_space_pct * 1.5)

        if side == Side.BUY:
            obstacle_price = prior_high
            if obstacle_price is None or bar.close >= obstacle_price:
                clean_space_pct = breakout_bonus_pct
                clean_space = True
            else:
                clean_space_pct = safe_div(obstacle_price - bar.close, bar.close)
                clean_space = clean_space_pct >= min_space_pct
            gap_fill_space_pct = abs(safe_div(bar.close - float(state.prior_close or bar.close), bar.close))
        else:
            obstacle_price = prior_low
            if obstacle_price is None or bar.close <= obstacle_price:
                clean_space_pct = breakout_bonus_pct
                clean_space = True
            else:
                clean_space_pct = safe_div(bar.close - obstacle_price, bar.close)
                clean_space = clean_space_pct >= min_space_pct
            gap_fill_space_pct = abs(safe_div(float(state.prior_close or bar.close) - bar.close, bar.close))

        minutes = max(int(state.last_minutes_since_open or 0), 0)
        window = max(float(cfg.get("opening_window_minutes", 15) or 15), 1.0)
        time_score = max(0.0, 1.0 - min(minutes / window, 1.0))
        space_score = min(max(safe_div(clean_space_pct, min_space_pct), 0.0), 1.0) if min_space_pct > 0 else 1.0
        gap_score = min(abs(float(state.gap_pct or 0.0)) / max(float(cfg.get("target_gap_pct", 0.01) or 0.01), 1e-9), 1.0)
        location_score = 1.0 if (location.near_20 or location.near_200) else 0.7 if location.extended_above_20 or location.extended_below_20 else 0.0
        atr_score = 0.0
        first_range = abs(float(state.first_high or 0.0) - float(state.first_low or 0.0))
        if atr and atr > 0 and first_range > 0:
            atr_score = min(first_range / atr, 1.0)
        score = (time_score * 0.25) + (space_score * 0.35) + (gap_score * 0.15) + (location_score * 0.2) + (atr_score * 0.05)

        return {
            "score": round(score, 4),
            "time_score": round(time_score, 4),
            "space_score": round(space_score, 4),
            "gap_score": round(gap_score, 4),
            "location_score": round(location_score, 4),
            "clean_space": bool(clean_space),
            "clean_space_pct": round(clean_space_pct, 6),
            "gap_fill_space_pct": round(gap_fill_space_pct, 6),
            "obstacle_price": obstacle_price,
            "prior_structure_high": prior_high,
            "prior_structure_low": prior_low,
        }

    def _opening_metadata(self, variant: str, state: OpeningGapState, metrics: dict, atr: Optional[float]) -> dict:
        return {
            "setup_family": "opening_gap_time_space",
            "play_variant": variant,
            "prior_close": state.prior_close,
            "gap_direction": state.gap_direction,
            "gap_pct": state.gap_pct,
            "gap_fill_price": state.prior_close,
            "first_open": state.first_open,
            "first_high": state.first_high,
            "first_low": state.first_low,
            "first_close": state.first_close,
            "opening_bars_seen": state.bars_seen,
            "minutes_since_open": state.last_minutes_since_open,
            "time_space_score": metrics.get("score"),
            "time_score": metrics.get("time_score"),
            "space_score": metrics.get("space_score"),
            "clean_space": metrics.get("clean_space"),
            "clean_space_pct": metrics.get("clean_space_pct"),
            "gap_fill_space_pct": metrics.get("gap_fill_space_pct"),
            "obstacle_price": metrics.get("obstacle_price"),
            "prior_structure_high": metrics.get("prior_structure_high"),
            "prior_structure_low": metrics.get("prior_structure_low"),
            "atr": atr,
        }

    def _prior_session_bars(self, ctx: VelezContext, session_date: object, lookback: int) -> List[Bar]:
        selected = [
            item
            for item in ctx.bars
            if self._local_timestamp(item.timestamp).date() != session_date
        ]
        if not selected:
            selected = list(ctx.bars)
        return selected[-max(int(lookback or 1), 1) :]

    def _local_timestamp(self, value: datetime) -> datetime:
        if value.tzinfo is None or ZoneInfo is None:
            return value
        tz_name = str(self.config.get("timezone") or self.config.get("session_timezone") or "America/New_York")
        if tz_name == "US/Eastern":
            tz_name = "America/New_York"
        try:
            return value.astimezone(ZoneInfo(tz_name))
        except Exception:
            return value

    def _minutes_since_open(self, local_dt: datetime) -> int:
        cfg = self.config.get("opening_gap", {})
        open_hour = int(cfg.get("session_open_hour", 9))
        open_minute = int(cfg.get("session_open_minute", 30))
        return (local_dt.hour * 60 + local_dt.minute) - (open_hour * 60 + open_minute)

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
            "event_candle_body": shape.body,
            "event_candle_range": shape.range,
            "body_range_pct": safe_div(shape.body, shape.range),
            "upper_wick_pct": safe_div(shape.upper_wick, shape.range),
            "lower_wick_pct": safe_div(shape.lower_wick, shape.range),
            "sma20": location.sma20,
            "sma200": location.sma200,
            "sma20_slope": location.sma20_slope,
            "sma200_slope": location.sma200_slope,
            "distance_to_sma20_pct": location.distance_to_sma20_pct,
            "close": bar.close,
            "timestamp": bar.timestamp,
            "management_plan": self._management_plan(side, bar.close if order_type == OrderType.MARKET else selected_limit, stop_price),
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

    def _bull_trend(self, location: LocationAssessment) -> bool:
        if location.sma20 is None:
            return False
        if location.sma200 is not None and location.sma20 < location.sma200:
            return False
        return self._slope_is_flat_or_rising(location.sma20_slope)

    def _bear_trend(self, location: LocationAssessment) -> bool:
        if location.sma20 is None:
            return False
        if location.sma200 is not None and location.sma20 > location.sma200:
            return False
        return self._slope_is_flat_or_declining(location.sma20_slope)

    def _recent_pullback(self, bars: List[Bar]) -> bool:
        if not bars:
            return False
        bearish = any(item.close < item.open for item in bars)
        lower_close = any(bars[i].close < bars[i - 1].close for i in range(1, len(bars)))
        return bearish or lower_close

    def _recent_pushup(self, bars: List[Bar]) -> bool:
        if not bars:
            return False
        bullish = any(item.close > item.open for item in bars)
        higher_close = any(bars[i].close > bars[i - 1].close for i in range(1, len(bars)))
        return bullish or higher_close

    def _color_add_metadata(self, direction: str, atr: Optional[float]) -> dict:
        return {
            "atr": atr,
            "position_intent": "mandatory_add_after_first_color_change",
            "scale_action": "add_to_winner",
            "add_fraction": self.config.get("color_change", {}).get("add_fraction", 0.5),
            "requires_existing_winner": True,
            "mandatory_add": True,
            "color_change_direction": direction,
        }

    def _management_plan(self, side: Side, entry_price: Optional[float], stop_price: float) -> dict:
        cfg = self.config.get("management", {})
        entry = float(entry_price or 0.0)
        risk = abs(entry - stop_price)
        first_r = float(cfg.get("first_target_r", 1.0))
        second_r = float(cfg.get("second_target_r", 2.0))
        sign = 1 if side == Side.BUY else -1
        return {
            "enabled": cfg.get("enabled", True),
            "first_target_r": first_r,
            "first_target_price": round(entry + sign * risk * first_r, 4) if risk > 0 else None,
            "first_take_profit_pct": cfg.get("first_take_profit_pct", 0.5),
            "second_target_r": second_r,
            "second_target_price": round(entry + sign * risk * second_r, 4) if risk > 0 else None,
            "bar_3_profit_check": True,
            "move_stop_to_breakeven_after_first_target": True,
            "bar_by_bar_trailing_after_bars": cfg.get("trail_after_bars", 3),
            "momentum_exhaustion_bars": cfg.get("momentum_exhaustion_bars", 5),
        }

    def _prioritized_signals(self, signals: List[Signal]) -> List[Signal]:
        if not signals:
            return []
        priority = {
            VelezPlay.OPENING_GAP_GO.value: 5,
            VelezPlay.OPENING_GAP_FADE.value: 6,
            VelezPlay.TIME_SPACE_BREAKOUT.value: 7,
            VelezPlay.BULL_180.value: 10,
            VelezPlay.BEAR_180.value: 10,
            VelezPlay.ELEPHANT.value: 20,
            VelezPlay.BOTTOMING_TAIL.value: 30,
            VelezPlay.TOPPING_TAIL.value: 30,
            VelezPlay.FAILED_NEW_HIGH.value: 40,
            VelezPlay.FAILED_NEW_LOW.value: 40,
            VelezPlay.COLOR_CHANGE_ADD.value: 50,
            VelezPlay.BUY_SETUP.value: 60,
            VelezPlay.SELL_SETUP.value: 60,
            VelezPlay.NRB_ACORN.value: 70,
            VelezPlay.FAB4_TRAP_BREAKOUT.value: 80,
        }
        selected: Dict[Side, Signal] = {}
        for signal in sorted(signals, key=lambda item: priority.get(str(item.metadata.get("play") or item.reason), 999)):
            if signal.side not in selected:
                selected[signal.side] = signal
        return list(selected.values())

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
