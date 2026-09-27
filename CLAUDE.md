# velez-swing-bot — trading doctrine (read before changing strategy, entries, exits or config)

This bot trades Oliver Velez's method the way the owner designed it. The rules
below are **non-negotiable**. Don't loosen them to "get more trades", to make
a backtest look better, or to make a failing test pass. If a change appears to
need that, stop and ask the owner.

## The rulebook

- `bot/core/velez_doctrine.py` is vendored **byte-for-byte** from `velez-mcp/velez.py`.
  It's the one rulebook shared by the MCP and every bot (trading bot, swing bot,
  Bull Pilot, Bull Swarm).
- Don't edit it here. Change `velez-mcp/velez.py`, bump `DOCTRINE_VERSION`, re-copy,
  and update `DOCTRINE_SHA256` in `bot/tests/test_velez_doctrine.py`.
- Reference material (videos, market-states table): `velez-mcp/docs/VELEZ_REFERENCES.md`.

## Non-negotiables

1. **Two lines run everything.** The 20 SMA is the trend. The **200 SMA is a veto**:
   it removes trades and never creates them. No longs under a non-rising 200, no
   shorts over a non-falling 200. The only exception is a reversal play *at* the 200.
2. **Market state decides the play before the candle does.**
   - **Narrow (the coil):** play explosions out of it (elephant bars).
   - **Trending (the move):** play color changes at or near the 20.
   - **Wide (the climax):** never buy or short the trend. Take profits, or fade/reverse.
3. **Location first.** Continuation entries happen at the 20/200. Reversals need price
   stretched from the 20, or testing the 200. Tails at a rising 20 are continuation buys.
4. **Exhausting elephants are exits, not entries.** An elephant born far from the 20
   after a run is where you sell, never where you buy.
5. **Enter on the break of the event bar**, never its close. Elephant, 180, tails and
   failed highs/lows arm on the event bar and fire only when a later bar trades through it.
   - If the break runs away, bid the breakout level. Don't chase.
   - A planned 50% retrace limit (big elephant, tail) is also allowed.
6. **Event stop:** one tick beyond the event bar. If that stop is too wide for the risk
   budget, size down; never tighten the stop inside the bar.
7. **Management:**
   - 1R: stop to breakeven. A winner never turns into a loser.
   - Two closes in favor: trail one tick behind the prior bar, bar by bar.
   - **3-bar rule:** not working after 3 bars means out.
   - Opposing tail, 180 or elephant: tighten to that bar.
   - Sell into exhausting elephants.
8. **Adds** go only on winners, on the first color change (RBI/GBI), at no more than
   50% of current size.
9. This bot trades **daily bars**. Bar-count rules are counted in days here: the
   break window is the next day, and the 3-bar rule means 3 days. The market-state gap
   thresholds are set for daily charts (`narrow_state_pct: 0.02`, `wide_state_pct: 0.10`).

## Where it's enforced

| Rule | Code |
|---|---|
| Entry gate (200 veto, wide state, exhaustion), market state, break-of-bar arming | `bot/core/velez_strategy.py` → `_apply_doctrine`, `_fire_armed` |
| Tail at a rising/falling 20 | `bot/core/velez_strategy.py` → `_tail_signals` (`continuation_at_20`) |
| Backtest exits (breakeven, bar-by-bar trail, 3-bar rule) | `bot/backtest/engine.py` → `_velez_manage` |
| Live exits | `bot/webhook_server.py` → `_velez_live_management` (inside `_auto_lifecycle_actions`, still gated by `VELEZ_LIFECYCLE_AUTO_EXECUTE`) |
| Config | `bot/config.yaml` → `velez_strategy.doctrine` |
| Lock-in tests | `bot/tests/test_velez_doctrine.py` |

## Changing things safely

- Which plays are *live* is a separate, evidence-based decision: `enabled:` flags and
  `setup_allowlist`. Only turn a play on after it passes fit/holdout validation.
- Detector unit tests (`test_velez_setup_allowlist.py`)
  turn the doctrine off on purpose so they test the detector alone. New strategy
  tests should keep the doctrine **on**.
- Run the suite with Python 3.12: `python -m pytest -q`.
