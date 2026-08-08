from datetime import datetime, timedelta

import pytest

from bot.core.types import Bar
from bot.core.vwap_engine import VWAPEngine, attach_vwap_metadata, merged_vwap_config, score_vwap_context, vwap_hard_filter_reason


def bar(index, close, *, high=None, low=None, volume=100, day=3, hour=9, minute=30):
    high = close if high is None else high
    low = close if low is None else low
    return Bar(
        timestamp=datetime(2026, 8, day, hour, minute) + timedelta(minutes=index),
        open=close,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def test_session_vwap_uses_typical_price_times_volume_and_resets_daily():
    engine = VWAPEngine()
    first = engine.update(bar(0, 101, high=103, low=100, volume=10))
    second = engine.update(bar(1, 106, high=108, low=105, volume=30))
    # Typical prices are 101.333... and 106.333..., respectively.
    assert first.session_vwap == pytest.approx(101.3333333333)
    assert second.session_vwap == pytest.approx(105.0833333333)

    reset = engine.update(bar(0, 120, high=121, low=119, volume=25, day=4))
    assert reset.session_vwap == pytest.approx(120.0)


def test_price_position_and_slope_cover_above_below_rising_and_falling():
    rising = VWAPEngine({"slope_lookback": 2})
    rising.update(bar(0, 100), atr=1)
    above = rising.update(bar(1, 104), atr=1)
    assert above.position == "above"
    assert above.slope_label == "rising"
    assert above.long_alignment is True

    falling = VWAPEngine({"slope_lookback": 2})
    falling.update(bar(0, 100), atr=1)
    below = falling.update(bar(1, 96), atr=1)
    assert below.position == "below"
    assert below.slope_label == "falling"
    assert below.short_alignment is True


def test_slope_remains_useful_while_atr_is_warming_up():
    engine = VWAPEngine({"slope_lookback": 2})
    engine.update(bar(0, 100))
    state = engine.update(bar(1, 102))
    assert state.slope_label == "rising"


def test_reclaim_and_loss_require_closed_bar_confirmation():
    reclaim_engine = VWAPEngine({"reclaim_confirmation_bars": 2, "slope_lookback": 2})
    reclaim_engine.update(bar(0, 100), atr=1)
    reclaim_engine.update(bar(1, 96), atr=1)
    cross = reclaim_engine.update(bar(2, 104), atr=1)
    confirmed = reclaim_engine.update(bar(3, 106), atr=1)
    assert cross.cross_up is True
    assert cross.reclaim is False
    assert confirmed.reclaim is True

    loss_engine = VWAPEngine({"reclaim_confirmation_bars": 2, "slope_lookback": 2})
    loss_engine.update(bar(0, 100), atr=1)
    loss_engine.update(bar(1, 104), atr=1)
    cross = loss_engine.update(bar(2, 96), atr=1)
    confirmed = loss_engine.update(bar(3, 94), atr=1)
    assert cross.cross_down is True
    assert cross.loss is False
    assert confirmed.loss is True


def test_bounce_and_rejection_use_approach_then_confirmation():
    bounce_engine = VWAPEngine({"bounce_confirmation_bars": 1, "slope_lookback": 2})
    bounce_engine.update(bar(0, 100), atr=2)
    bounce_engine.update(bar(1, 104), atr=2)
    bounce_engine.update(bar(2, 103, high=104, low=101), atr=2)
    bounced = bounce_engine.update(bar(3, 106), atr=2)
    assert bounced.bounce is True

    rejection_engine = VWAPEngine({"bounce_confirmation_bars": 1, "slope_lookback": 2})
    rejection_engine.update(bar(0, 100), atr=2)
    rejection_engine.update(bar(1, 96), atr=2)
    rejection_engine.update(bar(2, 97, high=100, low=96), atr=2)
    rejected = rejection_engine.update(bar(3, 94), atr=2)
    assert rejected.rejection is True


def test_compression_extension_weekly_and_anchored_interfaces():
    compression = VWAPEngine({"slope_lookback": 2})
    compression.update(bar(0, 100), atr=2)
    compressed = compression.update(bar(1, 100.1), atr=2)
    assert compressed.compression is True

    extended = compression.update(bar(2, 110), atr=2)
    assert extended.extension is True

    weekly = VWAPEngine({"weekly_vwap": True, "primary_variant": "weekly", "anchored_vwap": True})
    first = weekly.update(bar(0, 100, day=3), atr=1)
    second = weekly.update(bar(0, 110, day=4), atr=1)
    assert first.weekly_vwap == pytest.approx(100.0)
    assert second.weekly_vwap == pytest.approx(105.0)
    weekly.set_anchor("manual_breakout", datetime(2026, 8, 4, 9, 30))
    anchored = weekly.update(bar(1, 112, day=4), atr=1)
    assert anchored.anchored_vwap["manual_breakout"] == pytest.approx(112.0)


def test_score_reasons_are_explicit_and_bidirectional():
    engine = VWAPEngine({"slope_lookback": 2})
    engine.update(bar(0, 100), atr=4)
    context = engine.update(bar(1, 102), atr=4)
    confluence = score_vwap_context(
        context,
        "buy",
        engine.config,
        {"play": "bull_180", "sma20": 103, "sma200": 99, "volume_ratio": 1.5},
    )
    assert confluence.score >= 8
    assert confluence.classification in {"STRONG VWAP CONFLUENCE", "PREMIUM VWAP CONFLUENCE"}
    assert any("price is on" in reason for reason in confluence.reasons)
    assert any("slope" in reason for reason in confluence.reasons)

    bearish = VWAPEngine({"slope_lookback": 2})
    bearish.update(bar(0, 100), atr=4)
    down = bearish.update(bar(1, 98), atr=4)
    short = score_vwap_context(down, "sell", bearish.config, {"play": "bear_180"})
    assert short.score >= 8


def test_disabling_vwap_is_safe_and_hard_filter_defaults_off():
    cfg = merged_vwap_config({"enabled": False})
    assert cfg["hard_filter_enabled"] is False
    engine = VWAPEngine(cfg)
    context = engine.update(bar(0, 100), atr=1)
    assert context.available is False
    assert context.reason == "disabled"
    metadata = {"play": "elephant_bar", "entry_price": 100, "stop_price": 99}
    attach_vwap_metadata(metadata, context, "buy", cfg)
    assert metadata["entry_price"] == 100
    assert metadata["stop_price"] == 99
    assert metadata["vwap_score"] == 0
    assert metadata["vwap_confluence"] == "NEUTRAL"


def test_bias_and_setup_confluence_switches_are_honored():
    engine = VWAPEngine({"slope_lookback": 2})
    engine.update(bar(0, 100), atr=4)
    context = engine.update(bar(1, 102), atr=4)
    without_bias = score_vwap_context(context, "buy", {"bias_enabled": False}, {"play": "bull_180"})
    without_label = score_vwap_context(context, "buy", {"setup_confluence_enabled": False}, {"play": "bull_180"})
    assert without_bias.score == 0
    assert without_label.classification == "NEUTRAL"


def test_optional_hard_filter_is_off_by_default_and_only_blocks_strong_opposition():
    engine = VWAPEngine({"slope_lookback": 2})
    engine.update(bar(0, 100), atr=4)
    opposed = engine.update(bar(1, 98), atr=4)
    assert opposed.short_alignment is True
    assert vwap_hard_filter_reason(opposed, "buy", {}) is None
    assert vwap_hard_filter_reason(opposed, "buy", {"hard_filter_enabled": True}) == "vwap_hard_filter:opposite_price_and_slope_alignment"


def test_zero_volume_and_extended_hours_are_not_silently_mixed():
    engine = VWAPEngine()
    zero = engine.update(bar(0, 100, volume=0), atr=1)
    assert zero.available is False
    assert zero.reason == "missing_or_zero_volume"
    premarket = engine.update(bar(0, 100, hour=8), atr=1)
    assert premarket.available is False
    assert premarket.reason == "outside_configured_session"
