# Strategy Spec

**Disclaimer:** Educational use only. Not financial advice.

## Velez Institutional Strategy

The live webhook uses `bot/core/velez_strategy.py` for the Oliver Velez playbook. Every setup must qualify by structural location around the 20 SMA, extension from the 20 SMA, or the 200 SMA.

Implemented plays:

- Elephant Bar Play.
- Bull 180 and Bear 180.
- Bottoming Tail and Topping Tail.
- Velez Buy Setup and Sell Setup.
- NRB/Acorn continuation break.
- First Color-Change Add, sized as a guarded 50% add to an existing winner.
- Fab 4 trap-zone breakout.
- Failed New High and Failed New Low.
- Opening Gap Go and Opening Gap Fade.
- Opening-range Time + Space Breakout.

Every signal carries entry, stop, order type, no-chase status, SMA location, and a Velez-style management plan with 1R/2R targets, bar-3 review, breakeven move, trailing guidance, and exhaustion watch.

## Opening Gap / Time + Space Layer

The V6.15 opening module evaluates the first regular-session bars through a Velez-style context lens:

- **Gap direction and size:** compares the first regular-session open to the prior daily/session close.
- **Time:** only acts during the configured opening window, defaulting to the first 15 minutes for gap plays and first 30 minutes for time-space breakouts.
- **Space:** checks whether price has clean room before prior structure, or whether it is gapping directly into an obstacle.
- **First-bar control:** gap-and-go requires the first opening candle or early opening-range break to close with directional control.
- **Gap-fill/fade:** gap fades require rejection plus enough room back toward prior close.
- **Location discipline:** the play still needs valid 20 SMA, 200 SMA, or extension context.

New play names:

- `opening_gap_go`
- `opening_gap_fade`
- `time_space_breakout`

## Legacy Narrow To Wide Strategy

The original narrow-to-wide strategy remains in `bot/core/strategy.py` and is still documented below for research/backtest use.

## Indicators
- SMA(20)
- SMA(200)
- ATR(14)
- Optional EMA(9) for power-move confirmation

## Regime
- **Bull:** Close > SMA200 and SMA200 slope > 0
- **Bear:** Close < SMA200 and SMA200 slope < 0
- **Neutral:** Otherwise (reduce size or no trades)

SMA200 slope is computed over `slope_lookback` bars: `(SMA200_t - SMA200_{t-N}) / (N-1)`.

## Narrow vs Wide State
- Spread: `abs(SMA20 - SMA200) / Close`
- **Narrow:** Spread below `narrow_threshold` for `narrow_bars` AND ATR% declining over the same window
- **Wide:** Spread above `wide_threshold` OR breakout bar (range > `breakout_atr_mult` * ATR)
- Hysteresis: separate narrow and wide thresholds to reduce flip-flops

## Entry
Long (Bull regime only):
1. Narrow state transitions to Wide (N→W)
2. Breakout trigger (configurable):
   - SMA20 cross with momentum, or
   - Break above recent swing high (lookback `swing_lookback`)
3. Optional bar quality filter (Elephant bar approximation)
4. Optional EMA(9) power-move confirmation
5. Enter on next bar open (or limit at breakout level)

Short (Bear regime only): mirror conditions.

## Exit
- Initial stop: ATR or structure-based (recent swing low/high)
- Trailing stop: ATR or SMA20-based with debounce
- Partial exits: 1R and 2R defaults (move stop to breakeven after first partial)
- Time stop: if no meaningful move after N bars

## No Lookahead / No Repaint
- Signals are computed only with historical bars up to the close of the signal bar
- Entries are placed for the next bar open
- Stops and targets are simulated using bar OHLC (conservative ordering)

## State Diagram (Simplified)

```
NARROW  --(spread>wide OR breakout_bar)-->  WIDE
  ^                                            |
  |--(spread<narrow AND atr% declining)--------|
```
