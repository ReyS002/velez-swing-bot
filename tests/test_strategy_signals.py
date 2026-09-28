from datetime import datetime, timedelta

from bot.core.strategy import NarrowToWideStrategy
from bot.core.types import Bar, Side
from bot.core.utils import get_logger


def test_strategy_generates_signal():
    cfg = {
        "sma_fast": 2,
        "sma_slow": 3,
        "atr_period": 2,
        "slope_lookback": 2,
        "narrow_threshold": 0.002,
        "wide_threshold": 0.004,
        "narrow_bars": 2,
        "swing_lookback": 2,
        "breakout_mode": "sma_cross",
        "momentum_atr_mult": 0.0,
        "breakout_atr_mult": 10.0,
        "ema_power": False,
        "elephant": {"enabled": False},
    }
    logger = get_logger("test")
    strat = NarrowToWideStrategy(cfg, logger)

    start = datetime.utcnow()
    bars = [
        Bar(start, 100, 101, 99.5, 100, 1000),
        Bar(start + timedelta(minutes=1), 100, 100.8, 99.7, 100.0, 1000),
        Bar(start + timedelta(minutes=2), 100.0, 101.2, 99.8, 100.2, 1000),
        Bar(start + timedelta(minutes=3), 100.2, 100.9, 99.9, 100.1, 1000),
        Bar(start + timedelta(minutes=4), 100.1, 104.0, 100.0, 103.0, 1000),
    ]

    signals = []
    for bar in bars:
        signals = strat.on_bar("TEST", bar)

    assert signals
    assert signals[0].side == Side.BUY
