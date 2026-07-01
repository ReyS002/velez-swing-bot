# Strategy Spec (Narrow to Wide)

**Disclaimer:** Educational use only. Not financial advice.

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

