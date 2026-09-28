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
        "buy_sell_setup": {"enabled": True, "pullback_bars": 2},
        "nrb_acorn": {"enabled": True, "range_lookback": 3, "max_range_mult": 0.65, "max_atr_mult": 0.55},
        "color_change": {"enabled": True, "add_fraction": 0.5},
        "fab4": {
            "enabled": True,
            "breakout_lookback": 3,
            "max_sma_spread_pct": 0.02,
            "max_sma_spread_atr_mult": 2.0,
            "max_zone_atr_mult": 5.0,
        },
        "failed_breakout": {"enabled": True, "structure_lookback": 3, "min_rejection_wick_pct": 0.35},
        "opening_gap": {
            "enabled": True,
            "session_open_hour": 9,
            "session_open_minute": 30,
            "opening_window_minutes": 15,
            "max_signal_bars": 3,
            "min_gap_pct": 0.003,
            "max_gap_pct": 0.08,
            "target_gap_pct": 0.01,
            "min_clean_space_pct": 0.004,
            "breakout_space_bonus_pct": 0.008,
            "min_time_space_score": 0.65,
            "first_bar_close_position_pct": 0.65,
            "fade_rejection_wick_pct": 0.35,
            "min_gap_fill_space_pct": 0.002,
            "structure_lookback": 5,
        },
        "time_space": {
            "enabled": True,
            "opening_window_minutes": 30,
            "min_bars_after_open": 2,
            "max_signal_bars": 6,
            "max_neutral_gap_pct": 0.003,
            "min_clean_space_pct": 0.004,
            "breakout_space_bonus_pct": 0.008,
            "min_time_space_score": 0.65,
            "target_gap_pct": 0.01,
            "structure_lookback": 5,
        },
        "management": {"enabled": True, "first_target_r": 1.0, "second_target_r": 2.0, "first_take_profit_pct": 0.5},
    }
    base.update(overrides)
    return base


def only_new_play(name):
    disabled = {
        "elephant": {"enabled": False},
        "one_eighty": {"enabled": False},
        "tail": {"enabled": False},
        "buy_sell_setup": {"enabled": name == "buy_sell_setup", "pullback_bars": 2},
        "nrb_acorn": {"enabled": name == "nrb_acorn", "range_lookback": 3, "max_range_mult": 0.65, "max_atr_mult": 0.55},
        "color_change": {"enabled": name == "color_change", "add_fraction": 0.5},
        "fab4": {
            "enabled": name == "fab4",
            "breakout_lookback": 3,
            "max_sma_spread_pct": 0.02,
            "max_sma_spread_atr_mult": 2.0,
            "max_zone_atr_mult": 5.0,
        },
        "failed_breakout": {"enabled": name == "failed_breakout", "structure_lookback": 3, "min_rejection_wick_pct": 0.35},
        "opening_gap": {
            "enabled": name == "opening_gap",
            "session_open_hour": 9,
            "session_open_minute": 30,
            "opening_window_minutes": 15,
            "max_signal_bars": 3,
            "min_gap_pct": 0.003,
            "max_gap_pct": 0.08,
            "target_gap_pct": 0.01,
            "min_clean_space_pct": 0.004,
            "breakout_space_bonus_pct": 0.008,
            "min_time_space_score": 0.65,
            "first_bar_close_position_pct": 0.65,
            "fade_rejection_wick_pct": 0.35,
            "min_gap_fill_space_pct": 0.002,
            "structure_lookback": 5,
        },
        "time_space": {
            "enabled": name == "time_space",
            "opening_window_minutes": 30,
            "min_bars_after_open": 2,
            "max_signal_bars": 6,
            "max_neutral_gap_pct": 0.003,
            "min_clean_space_pct": 0.004,
            "breakout_space_bonus_pct": 0.008,
            "min_time_space_score": 0.65,
            "target_gap_pct": 0.01,
            "structure_lookback": 5,
        },
    }
    return cfg(**disabled)


def bar(i, open_, high, low, close, volume=1000):
    return Bar(datetime(2026, 1, 1, 9, 30) + timedelta(minutes=i), open_, high, low, close, volume)


def session_bar(day, hour, minute, open_, high, low, close, volume=1000):
    return Bar(datetime(2026, 1, day, hour, minute), open_, high, low, close, volume)


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


def test_buy_setup_triggers_after_pullback_into_rising_sma():
    strategy = VelezInstitutionalStrategy(only_new_play("buy_sell_setup"), get_logger("test_velez_buy_setup"))
    bars = [
        bar(0, 100.0, 100.8, 99.9, 100.5),
        bar(1, 100.5, 101.3, 100.4, 101.0),
        bar(2, 101.0, 101.8, 100.9, 101.5),
        bar(3, 101.5, 102.3, 101.4, 102.0),
        bar(4, 102.0, 102.8, 101.9, 102.5),
        bar(5, 102.6, 102.7, 101.8, 102.0),
        bar(6, 102.0, 103.0, 101.9, 102.9),
    ]

    signals = run_bars(strategy, bars)

    assert signals
    assert signals[0].reason == "velez_buy_setup"
    assert signals[0].side == Side.BUY
    assert signals[0].metadata["management_plan"]["bar_3_profit_check"] is True


def test_nrb_acorn_triggers_on_break_of_narrow_pause_bar():
    strategy = VelezInstitutionalStrategy(only_new_play("nrb_acorn"), get_logger("test_velez_nrb"))
    bars = [
        bar(0, 100.0, 100.8, 99.9, 100.5),
        bar(1, 100.5, 101.3, 100.4, 101.0),
        bar(2, 101.0, 101.8, 100.9, 101.5),
        bar(3, 101.5, 102.3, 101.4, 102.0),
        bar(4, 102.0, 102.8, 101.9, 102.5),
        bar(5, 102.45, 102.55, 102.35, 102.5),
        bar(6, 102.5, 103.2, 102.4, 103.0),
    ]

    signals = run_bars(strategy, bars)

    assert signals
    assert signals[0].reason == "nrb_acorn"
    assert signals[0].metadata["nrb_range"] < signals[0].metadata["avg_range"]


def test_first_color_change_is_mandatory_add_candidate_once_per_leg():
    strategy = VelezInstitutionalStrategy(only_new_play("color_change"), get_logger("test_velez_color_change"))
    bars = [
        bar(0, 100.0, 100.8, 99.9, 100.5),
        bar(1, 100.5, 101.3, 100.4, 101.0),
        bar(2, 101.0, 101.8, 100.9, 101.5),
        bar(3, 101.5, 102.3, 101.4, 102.0),
        bar(4, 102.3, 102.4, 101.7, 101.9),
        bar(5, 101.9, 102.7, 101.8, 102.65),
    ]

    signals = run_bars(strategy, bars)

    assert signals
    assert signals[0].reason == "color_change_add"
    assert signals[0].metadata["mandatory_add"] is True
    assert signals[0].metadata["add_fraction"] == 0.5
    assert strategy.on_bar("TEST", bar(6, 102.7, 102.8, 102.1, 102.2)) == []
    assert strategy.on_bar("TEST", bar(7, 102.2, 103.0, 102.1, 102.95)) == []


def test_fab4_trap_breakout_triggers_from_compressed_sma_zone():
    strategy = VelezInstitutionalStrategy(only_new_play("fab4"), get_logger("test_velez_fab4"))
    bars = [
        bar(0, 100.0, 100.3, 99.8, 100.1),
        bar(1, 100.1, 100.4, 99.9, 100.0),
        bar(2, 100.0, 100.35, 99.85, 100.05),
        bar(3, 100.05, 100.45, 99.95, 100.1),
        bar(4, 100.1, 100.4, 99.9, 100.0),
        bar(5, 100.0, 101.0, 99.95, 100.9),
    ]

    signals = run_bars(strategy, bars)

    assert signals
    assert signals[0].reason == "fab4_trap_breakout"
    assert signals[0].metadata["sma_spread_pct"] <= 0.02


def test_failed_new_high_and_failed_new_low_reversal_traps():
    short_strategy = VelezInstitutionalStrategy(
        only_new_play("failed_breakout") | {"extended_sma_pct": 0.001, "extended_sma_atr_mult": 0.2},
        get_logger("test_velez_failed_high"),
    )
    short_bars = [
        bar(0, 100.0, 100.8, 99.9, 100.5),
        bar(1, 100.5, 101.3, 100.4, 101.0),
        bar(2, 101.0, 101.8, 100.9, 101.5),
        bar(3, 101.5, 102.3, 101.4, 102.0),
        bar(4, 102.0, 102.8, 101.9, 102.5),
        bar(5, 102.6, 104.0, 102.2, 102.7),
    ]
    short_signals = run_bars(short_strategy, short_bars)

    assert short_signals
    assert short_signals[0].reason == "failed_new_high"
    assert short_signals[0].side == Side.SELL

    long_strategy = VelezInstitutionalStrategy(
        only_new_play("failed_breakout") | {"extended_sma_pct": 0.001, "extended_sma_atr_mult": 0.2},
        get_logger("test_velez_failed_low"),
    )
    long_bars = [
        bar(0, 105.0, 105.1, 104.2, 104.5),
        bar(1, 104.5, 104.6, 103.7, 104.0),
        bar(2, 104.0, 104.1, 103.2, 103.5),
        bar(3, 103.5, 103.6, 102.7, 103.0),
        bar(4, 103.0, 103.1, 102.2, 102.5),
        bar(5, 102.4, 102.8, 101.0, 102.6),
    ]
    long_signals = run_bars(long_strategy, long_bars)

    assert long_signals
    assert long_signals[0].reason == "failed_new_low"
    assert long_signals[0].side == Side.BUY


def test_opening_gap_go_requires_first_bar_control_and_clean_space():
    strategy = VelezInstitutionalStrategy(
        only_new_play("opening_gap") | {"extended_sma_pct": 0.001, "extended_sma_atr_mult": 0.2},
        get_logger("test_velez_opening_gap_go"),
    )
    bars = [
        session_bar(1, 15, 50, 99.8, 100.0, 99.7, 99.9),
        session_bar(1, 15, 51, 99.9, 100.1, 99.8, 100.0),
        session_bar(1, 15, 52, 100.0, 100.2, 99.9, 100.1),
        session_bar(1, 15, 53, 100.1, 100.3, 100.0, 100.2),
        session_bar(1, 15, 54, 100.2, 100.4, 99.9, 100.0),
        session_bar(2, 9, 30, 102.0, 103.1, 101.8, 103.0, 2400),
    ]

    signals = run_bars(strategy, bars)

    assert signals
    signal = signals[0]
    assert signal.reason == "opening_gap_go"
    assert signal.side == Side.BUY
    assert signal.metadata["setup_family"] == "opening_gap_time_space"
    assert signal.metadata["gap_direction"] == "up"
    assert signal.metadata["gap_pct"] >= 0.019
    assert signal.metadata["clean_space"] is True
    assert signal.metadata["time_space_score"] >= 0.65


def test_opening_gap_fade_targets_gap_fill_after_rejection():
    strategy = VelezInstitutionalStrategy(
        only_new_play("opening_gap") | {"extended_sma_pct": 0.001, "extended_sma_atr_mult": 0.2},
        get_logger("test_velez_opening_gap_fade"),
    )
    bars = [
        session_bar(1, 15, 50, 99.8, 100.0, 99.7, 99.9),
        session_bar(1, 15, 51, 99.9, 100.1, 99.8, 100.0),
        session_bar(1, 15, 52, 100.0, 100.2, 99.9, 100.1),
        session_bar(1, 15, 53, 100.1, 100.3, 100.0, 100.2),
        session_bar(1, 15, 54, 100.2, 100.4, 99.9, 100.0),
        session_bar(2, 9, 30, 103.5, 104.2, 102.0, 102.2, 2600),
    ]

    signals = run_bars(strategy, bars)

    assert signals
    signal = signals[0]
    assert signal.reason == "opening_gap_fade"
    assert signal.side == Side.SELL
    assert signal.metadata["play_variant"] == "gap_fade_to_prior_close"
    assert signal.metadata["gap_fill_price"] == 100.0
    assert signal.metadata["gap_fill_space_pct"] > 0


def test_time_space_breakout_uses_opening_range_when_gap_is_small():
    strategy = VelezInstitutionalStrategy(
        only_new_play("time_space") | {"near_sma_pct": 0.05, "near_sma_atr_mult": 2.0},
        get_logger("test_velez_time_space_breakout"),
    )
    bars = [
        session_bar(1, 15, 50, 99.5, 99.7, 99.4, 99.6),
        session_bar(1, 15, 51, 99.6, 99.8, 99.5, 99.7),
        session_bar(1, 15, 52, 99.7, 99.9, 99.6, 99.8),
        session_bar(1, 15, 53, 99.8, 100.0, 99.7, 99.9),
        session_bar(1, 15, 54, 99.9, 100.1, 99.8, 100.0),
        session_bar(2, 9, 30, 100.1, 100.4, 99.9, 100.2, 1600),
        session_bar(2, 9, 32, 100.2, 101.1, 100.1, 101.0, 2200),
    ]

    signals = run_bars(strategy, bars)

    assert signals
    signal = signals[0]
    assert signal.reason == "time_space_breakout"
    assert signal.side == Side.BUY
    assert signal.metadata["play_variant"] == "opening_range_time_space_breakout"
    assert abs(signal.metadata["gap_pct"]) < 0.003
    assert signal.metadata["clean_space"] is True
