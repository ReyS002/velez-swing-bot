"""Tests for the setup allowlist -- one source of truth for what is live.

Ported from velez-trading-bot; both bots share the same strategy class and
must gate signals identically.

Restricting the live bot to elephant_bar previously meant setting
``enabled: false`` on nine scattered config blocks by hand. This gate makes
that one declaration. It sits ALONGSIDE the per-play flags, not instead of
them: a play's own flag decides whether its detector runs, this list decides
whether the detector's output is live-tradeable.

The default must be completely inert, which is asserted here against the
shipped config rather than a hand-written one.
"""

from datetime import datetime, timedelta

import pytest
import yaml

from bot.core.types import Bar, Side
from bot.core.velez_strategy import VelezInstitutionalStrategy, VelezPlay

ALL_PLAYS = {play.value for play in VelezPlay}


def cfg(**overrides):
    base = {
        "sma_fast": 20,
        "sma_slow": 50,
        "atr_period": 5,
        "slope_lookback": 5,
        "near_sma_pct": 0.03,
        "near_sma_atr_mult": 0.5,
        "extended_sma_pct": 0.02,
        "extended_sma_atr_mult": 2.0,
        "tick_size": {"default": 0.01},
        "entry": {"no_chase_body_pct": 0.05},
        "elephant": {"enabled": True, "body_lookback": 5, "structure_lookback": 5,
                     "min_body_mult": 1.8, "max_each_wick_pct": 0.2,
                     "max_total_wick_pct": 0.35, "climactic_body_mult": 99.0,
                     "climactic_atr_mult": 99.0},
        "one_eighty": {"enabled": True, "recover_pct": 0.8},
        "tail": {"enabled": True, "min_tail_pct": 0.66, "trend_bars": 3},
        "buy_sell_setup": {"enabled": True, "pullback_bars": 2},
        "nrb_acorn": {"enabled": True, "range_lookback": 3,
                      "max_range_mult": 0.65, "max_atr_mult": 0.55},
        "color_change": {"enabled": True, "add_fraction": 0.5},
        "fab4": {"enabled": False},
        "failed_breakout": {"enabled": False},
        "opening_gap": {"enabled": False},
        "time_space": {"enabled": False},
        "vwap": {"enabled": False},
        "management": {"enabled": True, "first_target_r": 1.0, "second_target_r": 2.0},
    }
    base.update(overrides)
    return base


def bar(i, o, h, l, c, v=1000):
    return Bar(datetime(2026, 1, 5, 9, 30) + timedelta(minutes=5 * i), o, h, l, c, v)


def noisy_series(n=90):
    """Enough movement that several different plays fire across the run."""
    rows, c = [], 100.0
    for i in range(n):
        step = 0.6 if (i // 6) % 2 == 0 else -0.5
        o = c
        c = o + step + (0.4 if i % 11 == 0 else -0.15)
        rows.append((o, max(o, c) + 0.3, min(o, c) - 0.3, c))
    # a wide-bodied bar to guarantee an elephant near the end
    o = rows[-1][3]
    rows.append((o, o + 4.2, o - 0.05, o + 4.0))
    return rows


def plays_fired(config):
    strategy = VelezInstitutionalStrategy(config)
    seen = []
    for i, (o, h, l, c) in enumerate(noisy_series()):
        for s in strategy.on_bar("TEST", bar(i, o, h, l, c)):
            seen.append(str(s.metadata["play"]))
    return seen


# --------------------------------------------------------------------------
# inert by default
# --------------------------------------------------------------------------

def test_absent_block_changes_nothing():
    config = cfg()
    baseline = plays_fired(config)
    config_with_empty = cfg(setup_allowlist={})
    assert plays_fired(config_with_empty) == baseline


def test_disabled_block_changes_nothing_even_with_lists_populated():
    """A populated list with enabled:false must still be inert."""
    baseline = plays_fired(cfg())
    loaded = cfg(setup_allowlist={
        "enabled": False,
        "allowed_plays": ["elephant_bar"],
        "excluded_plays": ["bull_180", "bear_180"],
    })
    assert plays_fired(loaded) == baseline


def test_shipped_config_is_inert():
    """Assert against the real config.yaml, not a hand-written stand-in."""
    shipped = yaml.safe_load(open("bot/config.yaml"))["velez_strategy"]
    block = shipped.get("setup_allowlist")
    assert block is not None, "block should be present and documented"
    assert block.get("enabled") is False
    status = VelezInstitutionalStrategy(shipped).describe_setup_allowlist()
    assert status["enabled"] is False
    assert set(status["effective_plays"]) == ALL_PLAYS, (
        "while disabled, every play must remain tradeable so live behaviour "
        "is governed solely by the per-play enabled flags"
    )


# --------------------------------------------------------------------------
# allow / exclude semantics
# --------------------------------------------------------------------------

def test_allowlist_keeps_only_named_plays():
    fired = plays_fired(cfg(setup_allowlist={
        "enabled": True, "allowed_plays": ["elephant_bar"],
    }))
    assert fired, "the allowed play should still fire"
    assert set(fired) == {"elephant_bar"}


def test_excludelist_drops_named_plays_and_keeps_the_rest():
    baseline = set(plays_fired(cfg()))
    assert len(baseline) > 1, "fixture must produce more than one play"
    victim = sorted(baseline - {"elephant_bar"})[0]
    fired = set(plays_fired(cfg(setup_allowlist={
        "enabled": True, "excluded_plays": [victim],
    })))
    assert victim not in fired
    assert fired == baseline - {victim}


def test_exclude_wins_over_allow_for_the_same_play():
    fired = plays_fired(cfg(setup_allowlist={
        "enabled": True,
        "allowed_plays": ["elephant_bar"],
        "excluded_plays": ["elephant_bar"],
    }))
    assert fired == []


def test_names_are_case_and_whitespace_insensitive():
    fired = plays_fired(cfg(setup_allowlist={
        "enabled": True, "allowed_plays": ["  ELEPHANT_BAR  "],
    }))
    assert set(fired) == {"elephant_bar"}


def test_empty_allowlist_without_require_explicit_permits_everything():
    baseline = plays_fired(cfg())
    fired = plays_fired(cfg(setup_allowlist={"enabled": True, "allowed_plays": []}))
    assert fired == baseline


def test_require_explicit_with_empty_allowlist_fails_closed():
    """Nothing signed off must mean nothing trades, never everything."""
    fired = plays_fired(cfg(setup_allowlist={
        "enabled": True, "allowed_plays": [], "require_explicit": True,
    }))
    assert fired == []


# --------------------------------------------------------------------------
# ordering: the gate must run before prioritisation
# --------------------------------------------------------------------------

def test_disallowed_high_priority_play_does_not_suppress_an_allowed_one():
    """The bug this ordering exists to prevent.

    _prioritized_signals keeps one signal per side by priority. bull_180/
    bear_180 outrank elephant_bar, so filtering after prioritisation would let
    an excluded 180 swallow the elephant that should have been taken.
    """
    config = cfg(setup_allowlist={"enabled": True, "allowed_plays": ["elephant_bar"]})
    strategy = VelezInstitutionalStrategy(config)
    control = VelezInstitutionalStrategy(cfg())

    elephants_allowlisted = 0
    elephants_unfiltered = 0
    for i, (o, h, l, c) in enumerate(noisy_series()):
        b = bar(i, o, h, l, c)
        elephants_allowlisted += sum(
            1 for s in strategy.on_bar("TEST", b)
            if s.metadata["play"] == VelezPlay.ELEPHANT.value
        )
        elephants_unfiltered += sum(
            1 for s in control.on_bar("TEST", b)
            if s.metadata["play"] == VelezPlay.ELEPHANT.value
        )
    assert elephants_allowlisted >= elephants_unfiltered, (
        "allowlisting elephant_bar must never yield FEWER elephants than "
        "running unfiltered -- that would mean a suppressed higher-priority "
        "play was still shadowing it"
    )
    assert elephants_allowlisted > 0


# --------------------------------------------------------------------------
# validation and introspection
# --------------------------------------------------------------------------

def test_unknown_play_name_is_rejected_at_construction():
    with pytest.raises(ValueError, match="unknown play"):
        VelezInstitutionalStrategy(cfg(setup_allowlist={
            "enabled": True, "allowed_plays": ["elephant"],  # missing _bar
        }))


def test_unknown_excluded_play_name_is_also_rejected():
    with pytest.raises(ValueError, match="unknown play"):
        VelezInstitutionalStrategy(cfg(setup_allowlist={
            "enabled": True, "excluded_plays": ["tail"],  # block name, not a play
        }))


def test_non_mapping_block_is_rejected():
    with pytest.raises(ValueError, match="must be a mapping"):
        VelezInstitutionalStrategy(cfg(setup_allowlist=["elephant_bar"]))


def test_validation_runs_even_when_the_gate_is_disabled():
    """A typo staged for later must be caught now, not on the day it goes live."""
    with pytest.raises(ValueError, match="unknown play"):
        VelezInstitutionalStrategy(cfg(setup_allowlist={
            "enabled": False, "allowed_plays": ["elephant"],
        }))


def test_describe_reports_the_effective_policy_and_its_rationale():
    status = VelezInstitutionalStrategy(cfg(setup_allowlist={
        "enabled": True,
        "allowed_plays": ["elephant_bar"],
        "reason": "only setup to pass the gate on a genuine holdout",
        "evidence": "smallcap_1h_fit_2021-12_2024-04_holdout_2024-04_2026-09",
    })).describe_setup_allowlist()
    assert status["effective_plays"] == ["elephant_bar"]
    assert status["enabled"] is True
    assert "holdout" in status["reason"]
    assert status["evidence"].startswith("smallcap_1h")


def test_describe_reflects_fail_closed_state():
    status = VelezInstitutionalStrategy(cfg(setup_allowlist={
        "enabled": True, "allowed_plays": [], "require_explicit": True,
    })).describe_setup_allowlist()
    assert status["effective_plays"] == []


def test_describe_excludes_are_reflected():
    status = VelezInstitutionalStrategy(cfg(setup_allowlist={
        "enabled": True, "excluded_plays": ["bull_180", "bear_180"],
    })).describe_setup_allowlist()
    assert "bull_180" not in status["effective_plays"]
    assert "bear_180" not in status["effective_plays"]
    assert "elephant_bar" in status["effective_plays"]
