# Agent Trading Core: Oliver Velez Institutional Strategy Package

Educational and paper-trading use only. This file defines the strategy rules implemented in `bot/core/velez_strategy.py`.

## System Prompt & Executive Overview

You are an autonomous execution agent running the Oliver Velez price action methodology. Your primary function is to locate, grade, and execute trades based on institutional footprints. You do not trade individual opinions; you trade major structural shifts relative to the 20-period Simple Moving Average (20 SMA) and 200-period Simple Moving Average (200 SMA).

## Universal Risk & Location Matrix

Every event must be qualified by structural location. An event without proper location is an automatic No-Trade.

- Location 1, At/Near the 20 SMA: high-velocity continuation or initial reversal zones. Max position sizing permitted.
- Location 2, Extremely Extended from 20 SMA: mean-reversion exhaustion zones. Position scaling must be defensive or contrarian.
- Location 3, At/Near the 200 SMA: major institutional battlegrounds. High probability of significant trend rejections or structural pivots.

## Skill 1: The Elephant Bar Play

An Elephant Bar is an institutional candlestick that is visually dominant, with a body significantly larger than at least the previous 3 to 5 candles and negligible upper/lower wicks.

### Bullish Trigger

A green Elephant Bar closes, breaking out of consolidation or crossing cleanly above a flat/rising 20 SMA or 200 SMA.

### Bearish Trigger

A red Elephant Bar closes, breaking down from consolidation or crossing cleanly below a flat/declining 20 SMA or 200 SMA.

### Execution

- Clearing Elephant Bar: enter the initial risk unit on the candle close if it clears prior structural highs/lows.
- 50% Retracement Entry: if the Elephant Bar is climactic or chased, queue a limit order at the midpoint of the Elephant Bar body.
- Stop: 1 tick past the opposite end of the Elephant Bar.

## Skill 2: Bull 180 & Bear 180 Reversal Plays

A 180-degree turn is a two-bar trap configuration that violently shifts immediate control.

- Bull 180: Bar 1 is red, Bar 2 is green.
- Bear 180: Bar 1 is green, Bar 2 is red.
- Mathematical condition: Bar 2 must recover at least 80% of Bar 1's body.
- Location filter: must occur directly at a key structural moving average.

### Execution

- Enter when Bar 2 crosses/sustains beyond the 80% recovery mark or on Bar 2 close.
- Bull 180 stop: 1 tick below the lowest low of the two-bar sequence.
- Bear 180 stop: 1 tick above the highest high of the two-bar sequence.

## Skill 3: Topping & Bottoming Tail Reversals

Tail bars represent failed auctions where an aggressive move was absorbed.

- Bottoming Tail: lower wick is at least 66% of the candle range.
- Topping Tail: upper wick is at least 66% of the candle range.

### Location Filter

- Bottoming Tail: actionable after an extended multi-bar decline far below the 20 SMA, or when testing a rising 200 SMA.
- Topping Tail: actionable after an extended multi-bar rally far above the 20 SMA, or when testing a declining 200 SMA.

### Execution

- Enter on the close of the Tail Bar, or place a limit entry at the 50% retracement of the tail.
- Stop: 1 tick past the extreme edge of the tail wick.

## Skill 4: Integrated Lot Sizing, Scaling, and Pyramiding

Let `R` be the maximum dollar risk budget allowed by account equity, fixed risk cap, leverage, and max-order guardrails. The bot now uses a Velez 1-to-4 lot conviction ladder before calculating units.

### 1-to-4 Lot Conviction Ladder

Lots scale the risk budget; they do not multiply beyond the configured max risk.

- 1 lot: 25% of `R`, starter or normal qualified setup.
- 2 lots: 50% of `R`, A/A+ event candle such as Elephant Bar, 180, Tail Bar, Opening Gap Go, or Time + Space Breakout.
- 3 lots: 75% of `R`, A+ setup at a position of power such as the 20 SMA or 200 SMA.
- 4 lots: 100% of `R`, rare best-case setup with power candle metrics, clean location, no chase, and clean stop.

The bot then calculates units from the selected lot risk budget:

```text
Units = Selected Lot Risk Budget / abs(Entry Price - Stop Loss Price)
```

The bot also applies contract multiplier, leverage, max quantity, and max stop-distance guardrails.

### Lot Guardrails

- Missing location caps the setup at 1 lot.
- Chased setups are capped defensively and use limit-entry behavior.
- Continuation setups far extended from the 20 SMA are capped defensively unless they are contrarian/reversal plays.
- Wide stops cap the setup below full size.
- The 200 SMA battle zone can increase lot conviction, but never beyond the configured max risk budget.

### 50% Pyramiding Rule

The bot is forbidden from adding to a losing position. It may add only when:

- the position is profitable,
- the initial risk has been mitigated, typically with the stop at breakeven or better,
- price forms a secondary pivot or minor pullback,
- the pullback/counter-trend volume is lower than recent volume.

When adding, the add size equals exactly 50% of the currently held position size, capped by original core capacity.

### Sizing Normalization

After a 50% partial take-profit, a new setup can scale the position back up only to the original 100% core unit capacity, never beyond the configured risk threshold.

## Skill 5: Velez Buy Setup & Sell Setup

The bot now scans classic controlled pullbacks into institutional moving-average structure.

- Buy Setup: trend is above/rising through the 20 SMA/200 SMA structure, price pulls back in a controlled way, then a bullish bar reclaims the prior pullback high or the 20 SMA.
- Sell Setup: mirror image below/falling through the 20 SMA/200 SMA structure.
- Stops: 1 tick beyond the pullback low/high sequence.
- Location rule: the setup must still occur at a valid 20 SMA or 200 SMA location.

## Skill 6: NRB / Acorn Bar

The NRB/Acorn module looks for a narrow-range pause bar inside a valid trend.

- Long trigger: a bullish bar breaks above the prior narrow-range bar.
- Short trigger: a bearish bar breaks below the prior narrow-range bar.
- Stops: 1 tick beyond the narrow-range bar.
- Purpose: lower-risk continuation or re-entry after the initial move.

## Skill 7: First Color-Change Add

The first meaningful color change after a pullback is treated as the mandatory add candidate, not a fresh full-core entry.

- Long add: bearish pullback bar followed by a bullish bar that clears the prior high in an uptrend.
- Short add: bullish pullback bar followed by a bearish bar that clears the prior low in a downtrend.
- Add sizing: exactly 50% of the currently held position.
- Guardrails: the bot requires an existing winning position and the add stop must show initial risk has been mitigated.

## Skill 8: Fab 4 Trap-Zone Breakout

The Fab 4 module marks compression where the 20 SMA, 200 SMA, price, and recent range are tight enough to create a trap zone.

- Long trigger: bullish close through the zone high.
- Short trigger: bearish close through the zone low.
- Stops: 1 tick beyond the opposite side of the compressed zone.

## Skill 9: Failed New High / Failed New Low

The bot scans for failed auctions at new extremes.

- Failed New High: price makes a fresh high, rejects, and closes back below prior structure after extension or a 200 SMA battle.
- Failed New Low: price makes a fresh low, rejects, and closes back above prior structure after extension or a 200 SMA battle.
- Stops: 1 tick past the failed extreme.

## Skill 10: Velez-Style Management Plan

Every generated setup now carries management metadata:

- Bar-3 profit check.
- 1R and 2R target prices.
- 50% first partial target.
- Move stop to breakeven after the first target.
- Bar-by-bar trailing after the momentum push develops.
- 3-to-5 bar exhaustion watch.

## Skill 11: Opening Gap / Time + Space Brain

The bot now treats the market open as a separate decision layer instead of forcing opening behavior into normal midday candle plays.

### Opening Gap Go

- Compares the first regular-session open to the prior close.
- Requires a configured minimum gap, default 0.30%.
- Requires first-bar directional control or an early opening-range break.
- Requires clean space before prior structure, plus valid 20 SMA / 200 SMA / extension context.
- Stop: 1 tick beyond the opening range.

### Opening Gap Fade

- Used when a gap rejects into extension, nearby structure, or 200 SMA pressure.
- Requires a rejection candle and enough space back toward the prior close.
- Uses the prior close as the gap-fill reference.
- Stop: 1 tick beyond the rejected opening extreme.

### Time + Space Breakout

- Used when the opening gap is too small to qualify as a true gap play.
- Waits for an early opening-range break with clean space before obstacles.
- Scores time, clean space, gap context, location, and range quality.

Every opening play carries metadata for `prior_close`, `gap_direction`, `gap_pct`, first opening range, `time_space_score`, clean-space status, obstacle price, and gap-fill price.

## Runtime Guardrails

- No chasing: if a setup has moved past its trigger by more than 5% of its body length, the bot cancels market execution and uses a 50% limit pullback.
- Volume validation: adds require lower/diminishing pullback volume. High-volume opposition requires risk reduction or tighter trailing stops.
- Paper-only default: Alpaca execution is blocked unless both config and `VELEZ_EXECUTE_ORDERS=true` arm order submission.
- Webhook authentication: TradingView webhooks must use a configured secret token.
