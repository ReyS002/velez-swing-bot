from datetime import datetime, timedelta

from bot.core.types import Bar, OrderType, Side
from bot.core.velez_strategy import (
    VelezInstitutionalStrategy,
    calculate_core_position_size,
    evaluate_pyramid_add,
)
from bot.core.utils import get_logger


def cfg(**overrides):
    base = {
        "sma_fast": 3,
        "sma_slow": 5,
        "atr_period": 2,
        "slope_lookback": 2,
        "near_sma_pct": 0.03,
        "near_sma_atr_mult": 0.5,
        "extended_sma_pct": 0.01,
        "extended_sma_atr_mult": 1.0,
        "tick_size": {"default": 0.01},
        "entry": {"no_chase_body_pct": 0.05},
        "elephant": {
            "enabled": True,
            "body_lookback": 3,
            "structure_lookback": 3,
            "min_body_mult": 1.8,
            "max_each_wick_pct": 0.2,
            "max_total_wick_pct": 0.35,
            "climactic_body_mult": 3.0,
            "climactic_atr_mult": 99.0,
        },
        "one_eighty": {"enabled": True, "recover_pct": 0.8},
        "tail": {"enabled": True, "min_tail_pct": 0.66, "trend_bars": 3, "prefer_tail_limit": True},
    }
    base.update(overrides)
    return base


def bar(i, open_, high, low, close, volume=1000):
    return Bar(datetime(2026, 1, 1, 9, 30) + timedelta(minutes=i), open_, high, low, close, volume)


def run_bars(strategy, bars):
    signals = []
    for item in bars:
        signals = strategy.on_bar("TEST", item)
    return signals


def test_elephant_bar_requires_location_and_builds_limit_when_chased():
    strategy = VelezInstitutionalStrategy(cfg(), get_logger("test_velez_elephant"))
    bars = [
        bar(0, 100.0, 100.4, 99.9, 100.2),
        bar(1, 100.2, 100.5, 100.0, 100.3),
        bar(2, 100.3, 100.6, 100.1, 100.4),
        bar(3, 100.4, 100.7, 100.2, 100.5),
        bar(4, 100.5, 100.8, 100.3, 100.6),
        bar(5, 100.6, 103.3, 100.5, 103.2),
    ]

    signals = run_bars(strategy, bars)

    assert signals
    signal = signals[0]
    assert signal.side == Side.BUY
    assert signal.reason == "elephant_bar"
    assert signal.metadata["order_type"] == OrderType.LIMIT.value
    assert signal.metadata["stop_price"] == 100.49
    assert signal.metadata["location"]


def test_no_location_blocks_otherwise_valid_elephant_bar():
    strategy = VelezInstitutionalStrategy(
        cfg(near_sma_pct=0.00001, near_sma_atr_mult=0.00001, extended_sma_pct=10.0, extended_sma_atr_mult=10.0),
        get_logger("test_velez_no_location"),
    )
    bars = [
        bar(0, 100.0, 100.4, 99.9, 100.2),
        bar(1, 100.2, 100.5, 100.0, 100.3),
        bar(2, 100.3, 100.6, 100.1, 100.4),
        bar(3, 100.4, 100.7, 100.2, 100.5),
        bar(4, 100.5, 100.8, 100.3, 100.6),
        bar(5, 103.0, 105.8, 102.9, 105.7),
    ]

    assert run_bars(strategy, bars) == []


def test_bull_180_recovers_80_percent_at_sma_location():
    strategy = VelezInstitutionalStrategy(cfg(), get_logger("test_velez_180"))
    bars = [
        bar(0, 100.0, 100.3, 99.9, 100.1),
        bar(1, 100.1, 100.5, 100.0, 100.3),
        bar(2, 100.3, 100.7, 100.2, 100.5),
        bar(3, 100.5, 100.8, 99.6, 99.7),
        bar(4, 99.7, 100.7, 99.6, 100.6),
    ]

    signals = run_bars(strategy, bars)

    assert any(signal.reason == "bull_180" for signal in signals)
    signal = next(signal for signal in signals if signal.reason == "bull_180")
    assert signal.side == Side.BUY
    assert signal.metadata["stop_price"] == 99.59
    assert signal.metadata["recovery_mark"] == 100.34


def test_bottoming_tail_uses_66_percent_tail_and_tail_midpoint_limit():
    strategy = VelezInstitutionalStrategy(cfg(near_sma_pct=0.002), get_logger("test_velez_tail"))
    bars = [
        bar(0, 109.0, 109.3, 107.8, 108.0),
        bar(1, 108.0, 108.2, 105.8, 106.0),
        bar(2, 106.0, 106.2, 103.8, 104.0),
        bar(3, 100.0, 100.3, 90.0, 100.2),
    ]

    signals = run_bars(strategy, bars)

    assert any(signal.reason == "bottoming_tail" for signal in signals)
    signal = next(signal for signal in signals if signal.reason == "bottoming_tail")
    assert signal.side == Side.BUY
    assert signal.metadata["order_type"] == "limit"
    assert signal.metadata["entry_price"] == 95.0
    assert signal.metadata["tail_pct"] >= 0.66


def test_position_size_and_pyramid_math():
    assert calculate_core_position_size(max_dollar_risk=1000, entry_price=50, stop_price=48, max_order_qty=10000) == 500

    decision = evaluate_pyramid_add(
        current_qty=500,
        entry_price=50,
        stop_price=50,
        current_price=52,
        current_volume=800,
        recent_volumes=[1200, 1100, 1000],
        max_core_qty=1000,
    )

    assert decision.allowed
    assert decision.qty == 250
