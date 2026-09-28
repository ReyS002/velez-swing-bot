# Trading Bull Desk decision intelligence

Version `v6.40.0` adds advisory decision support around the existing Velez strategy, risk, journal, lifecycle, calendar, and top-down engines. It does not add an order path or change any execution rule.

## Trade Readiness Score

The score is deterministic. Configuration lives at `trade_readiness.weights`; the defaults are:

| Component | Weight | Existing source |
|---|---:|---|
| Setup quality | 18% | persisted decision confidence receipt |
| Strategy alignment | 12% | top-down strategy activation |
| Higher-timeframe/regime alignment | 14% | daily and weekly top-down bias |
| Reward-to-risk | 14% | persisted entry, stop, target, and direction |
| Risk capacity | 14% | existing risk-status engine |
| Catalyst/context | 10% | existing calendar and earnings context |
| Data freshness | 9% | persisted decision timestamp |
| Guardrail state | 9% | existing decision result |

The formula is `round(sum(component score × configured weight))`. An unknown component contributes no points and its weight is excluded from evidence confidence; the score is not renormalized upward. Confidence is `round(sum(weights of known components) × 100)`. Each component carries status, source, source timestamp, a plain-English reason, and “Why this matters.”

An existing rejected/error decision is reported as an authoritative block. The readiness score never creates a new broker gate and never removes an existing gate.

## Risk and Execution Planner

`POST /api/planner/preview` is calculation-only. It uses broker-read account equity/buying power/positions, connected quote provenance, and the existing `RiskManager`, correlation check, aggregate-open-risk calculation, volatility breaker, and configured caps.

The planner validates directionally correct entry, stop, and targets; requires a written invalidation; calculates target R; and reports spread, freshness, buying power, same-symbol, correlation, and volatility evidence. Fractional sizing uses a new advisory method on the existing risk engine. The response always contains `can_stage: false`, `can_submit: false`, and `broker_read_only: true`.

Calculated size, maximum planned loss, notional, and R are explicitly estimates. Equity and buying power are broker-confirmed only when their source is `broker_account`. Invalid or unverifiable plans return `skip_trade`.

## Journal and performance formulas

Metrics use persisted `decisions`, `trade_outcomes`, and authenticated `trade_reviews` only:

- Win rate: positive-dollar-P/L records divided by records with known dollar P/L.
- Expectancy R: mean persisted or reconstructable realized R.
- Average win/loss: mean positive and negative persisted dollar P/L, respectively.
- Profit factor: gross positive dollar P/L divided by the absolute gross negative dollar P/L.
- Drawdown: largest chronological peak-to-trough decline in cumulative persisted dollar P/L.
- Sample size: count of joined closed outcome records.

The same formula block is used for all-history and rolling 7-, 30-, and 90-day views. Strategy, regime, symbol, direction, Eastern time-of-day, and weekday breakdowns use the same persisted records. Insufficient sample is displayed rather than padded with example data.

`trade_reviews` and `symbol_notes` are additive SQLite tables created with `CREATE TABLE IF NOT EXISTS`; there is no destructive migration. Reviews record planned-versus-actual evidence, tags, rule adherence, quality fields, skip classification, and notes. Symbol notes store private thesis, catalyst, key levels, risks, and invalidation.

## Missed trades and discipline

An untraded alert is classified as one of five states: intentionally skipped valid setup, missed valid setup, correctly avoided invalid setup, risk-blocked setup, or insufficient data. Unless a persisted decision or authenticated review proves another state, it defaults to insufficient data.

The Discipline Score averages only measurable process components and is hidden behind an adequate-sample threshold. Components cover planned risk, stop discipline, chasing, adds, setup authorization, trade frequency, session adherence, completed reviews, and valid skips. Profitability is returned separately. The language is neutral, evidence-linked, and the score never affects execution permissions.

## TradingView annotations

TradingView remains the chart engine with native candles. Verified entry, stop, targets, invalidation, and thesis levels appear in a synchronized adjacent layer and a TradingView symbol link. The application does not inspect, inject into, cover, or bypass the cross-origin TradingView iframe.
