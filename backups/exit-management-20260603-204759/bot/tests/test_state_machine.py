from bot.core.state_machine import StateMachine
from bot.core.types import NarrowWideState


def test_narrow_to_wide_transition():
    sm = StateMachine(narrow_threshold=0.01, wide_threshold=0.02, narrow_bars=2)

    # Feed narrow conditions
    snap1 = sm.update(close=100, sma20=100, sma200=100, sma200_slope=0.1, atr=1, breakout_bar=False)
    snap2 = sm.update(close=100, sma20=100.1, sma200=100, sma200_slope=0.1, atr=0.9, breakout_bar=False)

    assert sm.state == NarrowWideState.NARROW
    assert not snap2.transition_n2w

    # Trigger wide
    snap3 = sm.update(close=100, sma20=103, sma200=100, sma200_slope=0.1, atr=1.2, breakout_bar=True)
    assert snap3.transition_n2w
    assert sm.state == NarrowWideState.WIDE
