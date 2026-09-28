"""
Market-structure break-and-retest strategy.

Aggregates the incoming lower-timeframe (LTF) bar stream internally into a
higher-timeframe (HTF) series to establish swing structure and directional
bias, then looks for a retest of the broken HTF level on the LTF stream to
trigger entries. Both long and short setups are symmetric.

Research context (see conversation): the raw pattern backtests around a
45-60% win rate; the edge comes from stacking a trend/regime filter (this
HTF bias requirement) and demanding >=1:2 R:R, not from the pattern alone.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional

from .indicators import RollingATR
from .market_regime import classify_regime
from .types import Bar, Signal, Side


@dataclass
class BiasState:
    direction: Optional[str] = None
    broken_level: Optional[float] = None
    bars_since_break: int = 0
    retest_taken: bool = False


@dataclass
class SymbolContext:
    atr: RollingATR
    structure_lookback: int
    volume_lookback: int
    htf_highs: Deque[float] = field(default_factory=deque)
    htf_lows: Deque[float] = field(default_factory=deque)
    htf_volumes: Deque[float] = field(default_factory=deque)
    htf_bars: Deque[Bar] = field(default_factory=deque)
    htf_bucket_key: Optional[object] = None
    htf_open: Optional[float] = None
    htf_high: Optional[float] = None
    htf_low: Optional[float] = None
    htf_close: Optional[float] = None
    htf_volume: float = 0.0
    htf_last_ts: Optional[object] = None
    bias: BiasState = field(default_factory=BiasState)

    def __post_init__(self) -> None:
        self.htf_highs = deque(maxlen=self.structure_lookback)
        self.htf_lows = deque(maxlen=self.structure_lookback)
        self.htf_volumes = deque(maxlen=self.volume_lookback)
        self.htf_bars = deque(maxlen=80)


class StructureBreakRetestStrategy:
    """Break-of-structure + retest, with an internally aggregated HTF bias filter."""

    def __init__(self, config: dict, logger=None) -> None:
        self.config = config
        self.logger = logger
        self.symbols: Dict[str, SymbolContext] = {}

        self.htf_bucket = config.get("htf_bucket", "1D")  # "1D" or "4H"
        self.structure_lookback = config.get("structure_lookback", 10)
        self.max_retest_bars = config.get("max_retest_bars", 12)
        self.min_bars_since_break = config.get("min_bars_since_break", 2)
        self.retest_tolerance_atr = config.get("retest_tolerance_atr", 0.15)
        self.rejection_min_close_pct = config.get("rejection_min_close_pct", 0.5)
        self.stop_buffer_atr = config.get("stop_buffer_atr", 0.25)
        self.atr_period = config.get("atr_period", 14)
        self.min_break_atr_mult = config.get("min_break_atr_mult", 0.5)

        vol_cfg = config.get("volume_confirmation", {})
        self.volume_confirmation_enabled = vol_cfg.get("enabled", True)
        self.volume_lookback = vol_cfg.get("lookback", 10)
        self.volume_mult = vol_cfg.get("mult", 1.5)

        self.regime_gate_enabled = config.get("regime_gate_enabled", True)
        self.regime_config = {"market_regime": config.get("market_regime", {})}

    def _get_context(self, symbol: str) -> SymbolContext:
        if symbol not in self.symbols:
            self.symbols[symbol] = SymbolContext(
                atr=RollingATR(self.atr_period),
                structure_lookback=self.structure_lookback,
                volume_lookback=self.volume_lookback,
            )
        return self.symbols[symbol]

    def _htf_key(self, ts) -> object:
        if self.htf_bucket == "4H":
            return (ts.date(), (ts.hour // 4) * 4)
        return ts.date()

    def _volume_confirmed(self, ctx: SymbolContext) -> bool:
        if not self.volume_confirmation_enabled:
            return True
        if not ctx.htf_volumes:
            return True  # not enough history yet; don't block early bars
        avg_volume = sum(ctx.htf_volumes) / len(ctx.htf_volumes)
        if avg_volume <= 0:
            return True
        return ctx.htf_volume >= self.volume_mult * avg_volume

    def _close_htf_bar(self, ctx: SymbolContext) -> None:
        if ctx.htf_close is None:
            return
        prior_high = max(ctx.htf_highs) if ctx.htf_highs else None
        prior_low = min(ctx.htf_lows) if ctx.htf_lows else None
        atr = ctx.atr.atr
        min_clear = (self.min_break_atr_mult * atr) if atr else 0.0

        if prior_high is not None and ctx.htf_close > prior_high + min_clear and self._volume_confirmed(ctx):
            ctx.bias = BiasState(direction="bull", broken_level=prior_high)
        elif prior_low is not None and ctx.htf_close < prior_low - min_clear and self._volume_confirmed(ctx):
            ctx.bias = BiasState(direction="bear", broken_level=prior_low)

        ctx.htf_highs.append(ctx.htf_high)
        ctx.htf_lows.append(ctx.htf_low)
        ctx.htf_volumes.append(ctx.htf_volume)
        ctx.htf_bars.append(Bar(
            timestamp=ctx.htf_last_ts,
            open=ctx.htf_open,
            high=ctx.htf_high,
            low=ctx.htf_low,
            close=ctx.htf_close,
            volume=ctx.htf_volume,
        ))

    def _regime_ok(self, ctx: SymbolContext, direction: str) -> bool:
        """Block entries in regimes this pattern is known to fail in (choppy/range-bound,
        chaotic/volatile) rather than requiring an exact directional trending match at the
        retest bar itself — that condition turned out to almost never coincide with a
        genuine pullback-to-structure moment (the pullback itself dips price away from
        the "close to SMA" trending definition)."""
        if not self.regime_gate_enabled:
            return True
        if len(ctx.htf_bars) < 20:
            return True  # not enough history to classify confidently; don't block early bars
        regime = classify_regime(list(ctx.htf_bars), self.regime_config)
        return not regime.ranging and not regime.volatile

    def on_bar(self, symbol: str, bar: Bar) -> List[Signal]:
        ctx = self._get_context(symbol)
        atr = ctx.atr.update(bar)
        signals: List[Signal] = []

        key = self._htf_key(bar.timestamp)
        if ctx.htf_bucket_key is None or key != ctx.htf_bucket_key:
            if ctx.htf_bucket_key is not None:
                self._close_htf_bar(ctx)
            ctx.htf_bucket_key = key
            ctx.htf_open = bar.open
            ctx.htf_high = bar.high
            ctx.htf_low = bar.low
            ctx.htf_close = bar.close
            ctx.htf_volume = bar.volume
        else:
            ctx.htf_high = max(ctx.htf_high, bar.high)
            ctx.htf_low = min(ctx.htf_low, bar.low)
            ctx.htf_close = bar.close
            ctx.htf_volume += bar.volume
        ctx.htf_last_ts = bar.timestamp

        bias = ctx.bias
        if bias.direction is not None:
            bias.bars_since_break += 1
            if bias.bars_since_break > self.max_retest_bars:
                ctx.bias = BiasState()
                bias = ctx.bias

        retest_eligible = bias.bars_since_break >= self.min_bars_since_break
        if atr is not None and bias.direction is not None and retest_eligible and not bias.retest_taken and bias.broken_level is not None:
            level = bias.broken_level
            tolerance = self.retest_tolerance_atr * atr
            bar_range = max(bar.high - bar.low, 1e-9)

            if bias.direction == "bull":
                touched = bar.low <= level + tolerance
                close_pos = (bar.close - bar.low) / bar_range
                rejection = bar.close > bar.open and close_pos >= self.rejection_min_close_pct and bar.close > level
                if touched and rejection and self._regime_ok(ctx, "bull"):
                    stop_price = bar.low - self.stop_buffer_atr * atr
                    if bar.close > stop_price:
                        signals.append(Signal(
                            symbol=symbol,
                            side=Side.BUY,
                            reason="structure_break_retest",
                            metadata={
                                "regime": "bull",
                                "narrow_wide": "unknown",
                                "transition_n2w": True,
                                "spread": None,
                                "atr_percent": (atr / bar.close) if bar.close else None,
                                "atr": atr,
                                "swing_high": None,
                                "swing_low": level,
                                "stop_price": stop_price,
                                "broken_level": level,
                                "close": bar.close,
                                "timestamp": bar.timestamp,
                                "play": "structure_break_retest_long",
                            },
                        ))
                        bias.retest_taken = True

            elif bias.direction == "bear":
                touched = bar.high >= level - tolerance
                close_pos = (bar.high - bar.close) / bar_range
                rejection = bar.close < bar.open and close_pos >= self.rejection_min_close_pct and bar.close < level
                if touched and rejection and self._regime_ok(ctx, "bear"):
                    stop_price = bar.high + self.stop_buffer_atr * atr
                    if bar.close < stop_price:
                        signals.append(Signal(
                            symbol=symbol,
                            side=Side.SELL,
                            reason="structure_break_retest",
                            metadata={
                                "regime": "bear",
                                "narrow_wide": "unknown",
                                "transition_n2w": True,
                                "spread": None,
                                "atr_percent": (atr / bar.close) if bar.close else None,
                                "atr": atr,
                                "swing_high": level,
                                "swing_low": None,
                                "stop_price": stop_price,
                                "broken_level": level,
                                "close": bar.close,
                                "timestamp": bar.timestamp,
                                "play": "structure_break_retest_short",
                            },
                        ))
                        bias.retest_taken = True

        return signals

    def indicator_snapshot(self, symbol: str) -> dict:
        ctx = self.symbols.get(symbol)
        if ctx is None:
            return {}
        return {"atr": ctx.atr.atr, "sma_fast": None}

    def state_snapshot(self, symbol: str):
        return None
