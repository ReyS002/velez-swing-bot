from __future__ import annotations

from dataclasses import dataclass
from collections import deque
from typing import Deque, Dict, List, Optional

from .indicators import RollingSMA, RollingEMA, RollingATR, RollingSlope
from .state_machine import StateMachine
from .types import Bar, Signal, Side
from .utils import log_event


@dataclass
class SymbolContext:
    sma_fast: RollingSMA
    sma_slow: RollingSMA
    ema_power: Optional[RollingEMA]
    atr: RollingATR
    slope: RollingSlope
    state_machine: StateMachine
    swing_highs: Deque[float]
    swing_lows: Deque[float]
    prev_close: Optional[float] = None
    prev_sma_fast: Optional[float] = None
    prev_sma_slow: Optional[float] = None
    last_snapshot: Optional[object] = None


class NarrowToWideStrategy:
    def __init__(self, config: dict, logger) -> None:
        self.config = config
        self.logger = logger
        self.symbols: Dict[str, SymbolContext] = {}

    def _get_context(self, symbol: str) -> SymbolContext:
        if symbol in self.symbols:
            return self.symbols[symbol]

        cfg = self.config
        ema_enabled = cfg.get("ema_power", False)
        ctx = SymbolContext(
            sma_fast=RollingSMA(cfg.get("sma_fast", 20)),
            sma_slow=RollingSMA(cfg.get("sma_slow", 200)),
            ema_power=RollingEMA(cfg.get("ema_power_window", 9)) if ema_enabled else None,
            atr=RollingATR(cfg.get("atr_period", 14)),
            slope=RollingSlope(cfg.get("slope_lookback", 20)),
            state_machine=StateMachine(
                narrow_threshold=cfg.get("narrow_threshold", 0.004),
                wide_threshold=cfg.get("wide_threshold", 0.008),
                narrow_bars=cfg.get("narrow_bars", 10),
            ),
            swing_highs=deque(maxlen=cfg.get("swing_lookback", 20)),
            swing_lows=deque(maxlen=cfg.get("swing_lookback", 20)),
        )
        self.symbols[symbol] = ctx
        return ctx

    def on_bar(self, symbol: str, bar: Bar) -> List[Signal]:
        ctx = self._get_context(symbol)
        cfg = self.config
        signals: List[Signal] = []

        sma_fast = ctx.sma_fast.update(bar.close)
        sma_slow = ctx.sma_slow.update(bar.close)
        ema_power = ctx.ema_power.update(bar.close) if ctx.ema_power else None
        atr = ctx.atr.update(bar)
        sma200_slope = ctx.slope.update(sma_slow)

        breakout_bar = False
        if atr is not None:
            if (bar.high - bar.low) > cfg.get("breakout_atr_mult", 1.5) * atr:
                breakout_bar = True

        snapshot = ctx.state_machine.update(
            close=bar.close,
            sma20=sma_fast,
            sma200=sma_slow,
            sma200_slope=sma200_slope,
            atr=atr,
            breakout_bar=breakout_bar,
        )
        ctx.last_snapshot = snapshot

        swing_high = max(ctx.swing_highs) if ctx.swing_highs else None
        swing_low = min(ctx.swing_lows) if ctx.swing_lows else None

        momentum_ok = False
        if ctx.prev_close is not None and atr is not None:
            momentum_ok = abs(bar.close - ctx.prev_close) >= cfg.get("momentum_atr_mult", 0.5) * atr

        cross_above = (
            ctx.prev_close is not None
            and ctx.prev_sma_fast is not None
            and sma_fast is not None
            and ctx.prev_close <= ctx.prev_sma_fast
            and bar.close > sma_fast
        )
        cross_below = (
            ctx.prev_close is not None
            and ctx.prev_sma_fast is not None
            and sma_fast is not None
            and ctx.prev_close >= ctx.prev_sma_fast
            and bar.close < sma_fast
        )

        break_swing_high = swing_high is not None and sma_fast is not None and bar.close > swing_high and bar.close > sma_fast
        break_swing_low = swing_low is not None and sma_fast is not None and bar.close < swing_low and bar.close < sma_fast

        breakout_mode = cfg.get("breakout_mode", "either")
        long_trigger = False
        short_trigger = False
        if breakout_mode == "sma_cross":
            long_trigger = cross_above and momentum_ok
            short_trigger = cross_below and momentum_ok
        elif breakout_mode == "swing_break":
            long_trigger = break_swing_high
            short_trigger = break_swing_low
        else:
            long_trigger = (cross_above and momentum_ok) or break_swing_high
            short_trigger = (cross_below and momentum_ok) or break_swing_low

        elephant_ok_long = True
        elephant_ok_short = True
        if cfg.get("elephant", {}).get("enabled", False) and atr is not None:
            tr = max(
                bar.high - bar.low,
                abs(bar.high - (ctx.prev_close or bar.close)),
                abs(bar.low - (ctx.prev_close or bar.close)),
            )
            tr_ok = tr >= cfg["elephant"].get("range_atr_mult", 1.5) * atr
            bar_range = max(bar.high - bar.low, 1e-9)
            close_pos = (bar.close - bar.low) / bar_range
            elephant_ok_long = tr_ok and close_pos >= cfg["elephant"].get("close_pos_pct", 0.7)
            elephant_ok_short = tr_ok and (1 - close_pos) >= cfg["elephant"].get("close_pos_pct", 0.7)

        power_ok_long = True
        power_ok_short = True
        if cfg.get("ema_power", False) and ema_power is not None:
            power_ok_long = bar.close > ema_power
            power_ok_short = bar.close < ema_power

        if snapshot.transition_n2w:
            if snapshot.regime.value == "bull" and long_trigger and elephant_ok_long and power_ok_long:
                signals.append(
                    Signal(
                        symbol=symbol,
                        side=Side.BUY,
                        reason="narrow_to_wide_breakout",
                        metadata={
                            "regime": snapshot.regime.value,
                            "narrow_wide": snapshot.narrow_wide.value,
                            "spread": snapshot.spread,
                            "atr_percent": snapshot.atr_percent,
                            "transition_n2w": snapshot.transition_n2w,
                            "trigger": "long",
                            "atr": atr,
                            "sma_fast": sma_fast,
                            "sma_slow": sma_slow,
                            "swing_low": swing_low,
                            "swing_high": swing_high,
                            "close": bar.close,
                            "timestamp": bar.timestamp,
                        },
                    )
                )
                log_event(self.logger, "signal", {"symbol": symbol, "side": "buy", "reason": "n2w"})
            elif snapshot.regime.value == "bear" and short_trigger and elephant_ok_short and power_ok_short:
                signals.append(
                    Signal(
                        symbol=symbol,
                        side=Side.SELL,
                        reason="narrow_to_wide_breakout",
                        metadata={
                            "regime": snapshot.regime.value,
                            "narrow_wide": snapshot.narrow_wide.value,
                            "spread": snapshot.spread,
                            "atr_percent": snapshot.atr_percent,
                            "transition_n2w": snapshot.transition_n2w,
                            "trigger": "short",
                            "atr": atr,
                            "sma_fast": sma_fast,
                            "sma_slow": sma_slow,
                            "swing_low": swing_low,
                            "swing_high": swing_high,
                            "close": bar.close,
                            "timestamp": bar.timestamp,
                        },
                    )
                )
                log_event(self.logger, "signal", {"symbol": symbol, "side": "sell", "reason": "n2w"})

        ctx.prev_close = bar.close
        ctx.prev_sma_fast = sma_fast
        ctx.prev_sma_slow = sma_slow
        ctx.swing_highs.append(bar.high)
        ctx.swing_lows.append(bar.low)

        return signals

    def indicator_snapshot(self, symbol: str) -> dict:
        ctx = self.symbols.get(symbol)
        if ctx is None:
            return {}
        return {
            "sma_fast": ctx.prev_sma_fast,
            "sma_slow": ctx.prev_sma_slow,
            "atr": ctx.atr.atr,
        }

    def state_snapshot(self, symbol: str):
        ctx = self.symbols.get(symbol)
        if ctx is None:
            return None
        return ctx.last_snapshot
