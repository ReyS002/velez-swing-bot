"""Locks in the owner's Velez doctrine (see CLAUDE.md).

If one of these fails, the bot no longer trades the way it was designed to.
Fix the code, not the test -- unless the owner has changed the doctrine, in
which case change velez-mcp/velez.py first and re-vendor it.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from bot.backtest.engine import BacktestEngine
from bot.core import velez_doctrine as doctrine
from bot.core.types import Bar, Position, Side
from bot.core.velez_strategy import VelezInstitutionalStrategy

ROOT = Path(__file__).resolve().parents[1]
T0 = datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc)

# sha256 of core/velez_doctrine.py. Changing the rulebook is a deliberate act:
# update velez-mcp/velez.py, re-copy it, and update this hash in the same commit.
DOCTRINE_SHA256 = "590f0e24c46a4297e85a8184c5ea11c5e93ad25044e8851815949cf51a7c2926"


def cfg(**overrides):
    base = {
        "sma_fast": 20,
        "sma_slow": 50,
        "atr_period": 5,
        "slope_lookback": 5,
        "near_sma_pct": 0.004,
        "near_sma_atr_mult": 0.5,
        "extended_sma_pct": 0.012,
        "extended_sma_atr_mult": 1.0,
        "tick_size": {"default": 0.01},
        "entry": {"no_chase_body_pct": 0.05},
        "elephant": {"enabled": True, "body_lookback": 5, "structure_lookback": 5, "min_body_mult": 1.8,
                     "max_each_wick_pct": 0.2, "max_total_wick_pct": 0.35, "climactic_body_mult": 99.0,
                     "climactic_atr_mult": 99.0},
        "vwap": {"enabled": False},
        "doctrine": {"enabled": True, "narrow_state_pct": 0.001, "wide_state_pct": 0.03, "session_windows": False},
    }
    for key in ("one_eighty", "tail", "opening_gap", "time_space", "buy_sell_setup", "nrb_acorn", "fab4",
                "failed_breakout", "color_change"):
        base[key] = {"enabled": False}
    base.update(overrides)
    return base


def bar(i, o, h, l, c):
    return Bar(timestamp=T0 + timedelta(minutes=2 * i), open=o, high=h, low=l, close=c, volume=1000)


def uptrend(n=80, step=0.01):
    """Zig-zag uptrend: rising 20 above a rising 50, moderately apart."""
    rows, c = [], 100.0
    for i in range(n):
        o = c
        c = o + step + (0.04 if i % 2 else -0.03)
        rows.append((o, max(o, c) + 0.02, min(o, c) - 0.02, c))
    return rows


def with_pullback_and_elephant(rows, body=None):
    """Pullback to the 20, then an elephant. By default it closes one cent past the
    5-bar high it breaks (not chased), so the doctrine arms it for the break."""
    c = rows[-1][3]
    for _ in range(4):
        o, c = c, c - 0.06
        rows.append((o, o + 0.01, c - 0.01, c))
    o = c
    prior_high = max(r[1] for r in rows[-5:])
    close = o + body if body is not None else prior_high + 0.005
    rows.append((o, close + 0.01, o - 0.01, close))
    return rows


def run(strategy, rows, start=0):
    out = []
    for i, (o, h, l, c) in enumerate(rows):
        out.append(strategy.on_bar("TEST", bar(start + i, o, h, l, c)))
    return out


def elephant_setup():
    strategy = VelezInstitutionalStrategy(cfg())
    rows = with_pullback_and_elephant(uptrend())
    fired = run(strategy, rows)
    return strategy, rows, fired


# ── The rulebook itself ──

def test_vendored_rulebook_is_unchanged():
    digest = hashlib.sha256((ROOT / "core" / "velez_doctrine.py").read_bytes()).hexdigest()
    assert digest == DOCTRINE_SHA256, "core/velez_doctrine.py changed: re-vendor from velez-mcp and update the hash"


def test_shipped_config_keeps_the_doctrine_on():
    shipped = yaml.safe_load((ROOT / "config.yaml").read_text())["velez_strategy"]
    d = shipped["doctrine"]
    assert d["enabled"] is True
    assert d["break_of_event_bar"] is True
    assert d["exits"] is True and d["live_exits"] is True
    assert shipped["elephant"]["location_mode"] == "exclude_exhaustion"
    assert shipped["one_eighty"]["location_mode"] == "extended_or_200"
    assert shipped["tail"]["continuation_at_20"] is True


def test_doctrine_defaults_on_when_config_is_silent():
    strategy = VelezInstitutionalStrategy({k: v for k, v in cfg().items() if k != "doctrine"})
    assert strategy._doctrine_enabled()


# ── Entries: break of the event bar ──

def test_elephant_waits_for_the_break_then_enters_at_the_trigger():
    strategy, rows, fired = elephant_setup()
    assert fired[-1] == [], "must not buy the elephant's close"
    armed = strategy.symbols["TEST"].armed["buy"]
    event_o, event_h, event_l, event_c = rows[-1]
    assert armed["trigger"] == pytest.approx(event_h + 0.01)

    # Next bar trades one tick through the high and closes right there: market entry.
    nxt = run(strategy, [(event_c, event_h + 0.05, event_c - 0.02, event_h + 0.02)], start=len(rows))[0]
    assert len(nxt) == 1
    meta = nxt[0].metadata
    assert meta["play"] == "elephant_bar"
    assert meta["entry_type"] == "break_of_event_bar"
    assert meta["trigger_price"] == pytest.approx(event_h + 0.01)
    assert meta["stop_price"] == pytest.approx(event_l - 0.01)  # event stop
    assert meta["doctrine"]["allowed"] is True


def test_chased_elephant_uses_the_50_percent_retrace_limit_instead():
    strategy = VelezInstitutionalStrategy(cfg())
    rows = with_pullback_and_elephant(uptrend(), body=0.9)
    meta = run(strategy, rows)[-1][0].metadata
    o, _, _, c = rows[-1]
    assert meta["order_type"] == "limit"
    assert meta["limit_price"] == pytest.approx((o + c) / 2)
    assert strategy.symbols["TEST"].armed == {}


def test_no_chase_when_break_bar_runs_away():
    strategy, rows, _ = elephant_setup()
    _, event_h, _, event_c = rows[-1]
    nxt = run(strategy, [(event_c, event_h + 1.5, event_c - 0.02, event_h + 1.4)], start=len(rows))[0]
    meta = nxt[0].metadata
    assert meta["order_type"] == "limit"
    assert meta["limit_price"] == pytest.approx(event_h + 0.01)
    assert meta["chased"] is True


def test_setup_expires_without_a_break():
    strategy, rows, _ = elephant_setup()
    _, event_h, event_l, event_c = rows[-1]
    nxt = run(strategy, [(event_c, event_h - 0.05, event_c - 0.1, event_c - 0.05)], start=len(rows))[0]
    assert nxt == []
    assert "buy" not in strategy.symbols["TEST"].armed


def test_setup_dies_if_the_stop_trades_first():
    strategy, rows, _ = elephant_setup()
    _, event_h, event_l, event_c = rows[-1]
    nxt = run(strategy, [(event_c, event_h + 0.05, event_l - 0.05, event_c)], start=len(rows))[0]
    assert nxt == []


# ── Entries: the hard gates ──

def test_wide_state_refuses_trend_entries():
    strategy = VelezInstitutionalStrategy(cfg(doctrine={"enabled": True, "session_windows": False, "narrow_state_pct": 0.0001, "wide_state_pct": 0.001}))
    fired = run(strategy, with_pullback_and_elephant(uptrend()))
    assert fired[-1] == []
    assert strategy.symbols["TEST"].armed == {}
    assert strategy.symbols["TEST"].last_market_state["state"] == "wide"


def test_200_veto_blocks_longs_under_a_falling_200():
    g = doctrine.entry_gate("long", "elephant_bar", price=99, sma200=100, sma200_slope="falling",
                            state="trending", near_200=False)
    assert g["reasons"] == ["veto_200"]


def test_exhausting_elephant_is_never_an_entry_even_if_config_allows_it():
    g = doctrine.entry_gate("long", "elephant_bar", price=110, sma200=100, sma200_slope="rising",
                            state="trending", near_200=False, elephant_origin="exhausting")
    assert not g["allowed"]


def test_tail_at_rising_20_is_a_continuation_buy():
    strategy = VelezInstitutionalStrategy(cfg(tail={"enabled": True, "min_tail_pct": 0.66, "trend_bars": 3,
                                                    "prefer_tail_limit": True, "continuation_at_20": True},
                                              elephant={"enabled": False}))
    rows = uptrend(step=0.025)  # 20 well clear of the 200, so this is a 20 test, not a 200 test
    sma20 = sum(r[3] for r in rows[-20:]) / 20
    o = sma20 + 0.02
    rows.append((o, o + 0.02, o - 0.3, o + 0.01))  # long lower tail tagging the rising 20
    fired = run(strategy, rows)[-1]
    assert fired, strategy.symbols["TEST"].last_location
    meta = fired[0].metadata
    assert meta["play"] == "bottoming_tail"
    assert meta["setup_family"] == "continuation"
    assert meta["order_type"] == "limit"  # 50% of the tail


# ── Exits ──

def _position(entry=10.0, stop=9.5, qty=100):
    return Position(symbol="TEST", qty=qty, entry_price=entry, entry_time=T0, stop_price=stop,
                    initial_stop=stop, risk_per_share=abs(entry - stop))


def _engine_with(bars, position):
    config = yaml.safe_load((ROOT / "config.yaml").read_text())
    engine = BacktestEngine(config)
    ctx = engine.strategy._get_context("TEST")
    for b in bars:
        ctx.bars.append(b)
    engine.portfolio.positions["TEST"] = position
    engine.pending_orders["TEST"] = []
    engine.contract_multipliers["TEST"] = 1.0
    return engine


def test_backtest_uses_velez_bar_by_bar_trail_not_atr():
    bars = [bar(0, 10.0, 10.3, 9.95, 10.25), bar(1, 10.25, 10.6, 10.2, 10.55), bar(2, 10.55, 10.9, 10.5, 10.85)]
    pos = _position()
    engine = _engine_with(bars, pos)
    engine._update_trailing_stop("TEST", bars[-1])
    assert pos.stop_price == pytest.approx(10.19)  # one tick under the prior bar's low


def test_backtest_three_bar_rule_exits_a_trade_that_is_not_working():
    bars = [bar(0, 10.0, 10.1, 9.8, 9.95), bar(1, 9.95, 10.05, 9.8, 9.9), bar(2, 9.9, 10.0, 9.75, 9.85)]
    engine = _engine_with(bars, _position())
    engine._update_trailing_stop("TEST", bars[-1])
    assert [o.reason for o in engine.pending_orders["TEST"]] == ["velez_3_bar_rule"]


def test_live_lifecycle_moves_the_stop_bar_by_bar(monkeypatch):
    from bot import webhook_server

    bars = [bar(0, 10.0, 10.3, 9.95, 10.25), bar(1, 10.25, 10.6, 10.2, 10.55), bar(2, 10.55, 10.9, 10.5, 10.85)]

    class Stub:
        config = {"velez_strategy": {"doctrine": {"enabled": True, "live_exits": True}}}
        symbol_config = {}
        logger = None
        _float = staticmethod(lambda v: None if v is None else float(v))
        _timestamp = staticmethod(lambda v: v)
        _fetch_scanner_bars = staticmethod(lambda **kw: bars)
        _scanner_bar_is_closed = staticmethod(lambda b, now: True)

    position = {"symbol": "TEST", "side": "long", "entry_price": 10.0, "stop_price": 10.0,
                "linked_decision": {"timestamp": T0, "stop_price": 9.5}}
    decision = webhook_server.TradingViewWebhookEngine._velez_live_management(Stub(), position)
    assert decision["stop"] == pytest.approx(10.19)
    assert decision["action"] in {"take_partial", "trail"}


# ── Every entry source goes through the doctrine ──

def test_external_signals_are_gated_and_armed_like_engine_signals():
    from bot.core.types import Signal

    strategy = VelezInstitutionalStrategy(cfg(doctrine={"enabled": True, "session_windows": False, "narrow_state_pct": 0.0001, "wide_state_pct": 0.001}))
    rows = uptrend()
    run(strategy, rows)
    assert strategy.symbols["TEST"].last_market_state["state"] == "wide"
    ext = Signal("TEST", Side.BUY, "v_shape", {"play": "elephant_bar", "stop_price": 99.0})
    assert strategy.admit_external("TEST", [ext], bar(len(rows) - 1, *rows[-1])) == []
    assert ext.metadata["doctrine"]["reasons"] == ["wide_state_no_trend_entry"]


def test_external_event_play_is_armed_for_the_break():
    from bot.core.types import Signal

    strategy = VelezInstitutionalStrategy(cfg())
    rows = with_pullback_and_elephant(uptrend())[:-1]  # trending state, pulled back to the 20
    run(strategy, rows)
    assert strategy.symbols["TEST"].last_market_state["state"] == "trending"
    last = bar(len(rows) - 1, *rows[-1])
    ext = Signal("TEST", Side.BUY, "v_shape", {"play": "elephant_bar", "stop_price": last.low - 0.01})
    assert strategy.admit_external("TEST", [ext], last) == []
    assert strategy.symbols["TEST"].armed["buy"]["trigger"] == pytest.approx(last.high + 0.01)


def test_alert_for_unknown_symbol_is_tagged_unverified_not_silently_trusted():
    from bot.core.types import Signal

    strategy = VelezInstitutionalStrategy(cfg())
    sig = Signal("NEW", Side.BUY, "elephant_bar", {"play": "elephant_bar", "stop_price": 9.0})
    assert strategy.admit_external("NEW", [sig]) == [sig]
    assert sig.metadata["doctrine"]["verified"] is False


# ── Three-finger spread and adds (2026.09.3) ──

def _stretched_external(play, stretch_atr):
    """An external signal whose event bar opens `stretch_atr` ATRs above the rising 20."""
    from bot.core.types import Signal

    strategy = VelezInstitutionalStrategy(cfg())
    rows = uptrend()
    run(strategy, rows)
    ctx = strategy.symbols["TEST"]
    atr = ctx.last_market_state["atr"]
    assert atr
    o = ctx.last_location.sma20 + stretch_atr * atr
    event = bar(len(rows), o, o + 0.05, o - 0.01, o + 0.04)
    sig = Signal("TEST", Side.BUY, play, {"play": play, "stop_price": event.low - 0.01})
    return strategy, strategy.admit_external("TEST", [sig], event), sig


def test_continuation_is_never_chased_three_fingers_from_the_20():
    _, admitted, sig = _stretched_external("elephant_bar", 3.5)
    assert admitted == []
    assert "three_finger_spread_chase" in sig.metadata["doctrine"]["reasons"]


def test_continuation_near_the_20_is_not_a_spread_chase():
    _, _, sig = _stretched_external("elephant_bar", 0.5)
    assert "three_finger_spread_chase" not in sig.metadata["doctrine"]["reasons"]


def test_color_change_adds_only_in_p1_or_p2():
    _, admitted, sig = _stretched_external("color_change_add", 2.5)
    assert admitted == []
    assert "add_outside_p1_p2" in sig.metadata["doctrine"]["reasons"]
    _, _, early = _stretched_external("color_change_add", 0.5)
    assert "add_outside_p1_p2" not in early.metadata["doctrine"]["reasons"]


def test_immediate_plays_are_measured_where_they_fill():
    """An add that opens at the 20 but closes far from it fills late (P3/P4): not an add."""
    from bot.core.types import Signal

    strategy = VelezInstitutionalStrategy(cfg())
    rows = uptrend()
    run(strategy, rows)
    ctx = strategy.symbols["TEST"]
    atr, sma20 = ctx.last_market_state["atr"], ctx.last_location.sma20
    event = bar(len(rows), sma20, sma20 + 4 * atr, sma20 - 0.01, sma20 + 3.9 * atr)
    sig = Signal("TEST", Side.BUY, "color_change_add", {"play": "color_change_add", "stop_price": event.low - 0.01})
    assert strategy.admit_external("TEST", [sig], event) == []
    assert "add_outside_p1_p2" in sig.metadata["doctrine"]["reasons"]


# ── Session windows and trading with the market (2026.10.1) ──

LIVE_DOCTRINE = {"enabled": True, "narrow_state_pct": 0.001, "wide_state_pct": 0.03}


def test_shipped_config_keeps_session_and_market_rules_on():
    d = yaml.safe_load((ROOT / "config.yaml").read_text())
    section = d.get("velez_strategy") or d.get("bullpilot_strategy") or {}
    doctrine_cfg = section.get("doctrine", {})
    assert doctrine_cfg.get("session_windows", True) is True
    assert doctrine_cfg.get("market_bias", True) is True


def _external_elephant(event_index, spy_rows=None):
    """Warm up so the event bar sits at T0 + 2*event_index minutes (T0 = 10:00 ET)."""
    from bot.core.types import Signal

    strategy = VelezInstitutionalStrategy(cfg(doctrine=dict(LIVE_DOCTRINE)))
    rows = uptrend()
    start = event_index - len(rows)
    run(strategy, rows, start=start)
    if spy_rows is not None:
        strategy.update_market_index("SPY", [bar(start + i, *r) for i, r in enumerate(spy_rows)])
    c = rows[-1][3]
    event = bar(event_index, c, c + 0.3, c - 0.01, c + 0.28)
    sig = Signal("TEST", Side.BUY, "elephant_bar", {"play": "elephant_bar", "stop_price": event.low - 0.01})
    strategy.admit_external("TEST", [sig], event)
    return sig.metadata["doctrine"]["reasons"]


def test_no_trend_entries_in_the_midday_chop():
    assert "midday_chop" in _external_elephant(80)  # 12:40 ET


def test_first_fifteen_minutes_wait_then_prime_time_is_open():
    assert "opening_range_wait" in _external_elephant(-12)  # event 9:36, decision 9:38 ET
    reasons = _external_elephant(15)  # 10:30 ET
    assert not {"midday_chop", "opening_range_wait", "too_late_in_session"} & set(reasons)


def test_no_new_entries_into_the_close():
    assert "too_late_in_session" in _external_elephant(173)  # 15:46 ET


def test_trend_entries_only_with_the_market():
    down = [(200 - h, 200 - l, 200 - o, 200 - c) for o, h, l, c in [(r[0], r[1], r[2], r[3]) for r in uptrend()]]
    down = [(o, max(o, c) + 0.02, min(o, c) - 0.02, c) for o, _, _, c in down]
    assert "against_market" in _external_elephant(15, spy_rows=down)
    assert "against_market" not in _external_elephant(15, spy_rows=uptrend())
    assert "against_market" not in _external_elephant(15)  # no index data: not enforced
