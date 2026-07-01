from datetime import datetime

from bot.core.indicators import RollingSMA, RollingEMA, RollingATR
from bot.core.types import Bar


def test_rolling_sma():
    sma = RollingSMA(3)
    assert sma.update(1) is None
    assert sma.update(2) is None
    assert sma.update(3) == 2
    assert sma.update(4) == 3


def test_rolling_ema():
    ema = RollingEMA(3)
    assert ema.update(1) is None
    assert ema.update(2) is None
    val = ema.update(3)
    assert round(val, 5) == 2
    val = ema.update(4)
    assert round(val, 5) > 2


def test_rolling_atr():
    atr = RollingATR(2)
    bar1 = Bar(datetime.utcnow(), 10, 12, 9, 11, 100)
    bar2 = Bar(datetime.utcnow(), 11, 13, 10, 12, 100)
    assert atr.update(bar1) is None
    val = atr.update(bar2)
    assert val is not None
    assert round(val, 5) > 0
