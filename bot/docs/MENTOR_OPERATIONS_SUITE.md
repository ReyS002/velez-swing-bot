# Velez Mentor Operations Suite

Dashboard build: `v6.31`

Velez Mentor now exposes seven operations-grade tools from the Mentor tab and API. All tools are advisory-only; none can approve trades, submit orders, or change risk.

## Features

1. Chart Source Health
   - API: `GET /api/mentor/chart/source-health?symbol=SPY&timeframe=5Min`
   - Shows the active chart bar source, fallback order, rows loaded, and masked source configuration.
   - Equity fallback order is Alpaca stock bars → Tradier bars → yfinance bars.

2. Optional Screenshot Vision
   - Included in `POST /api/mentor/chart/observe`.
   - Default is disabled. When disabled, Mentor uses connected bars, journal context, and screenshot metadata only.
   - Optional provider env:
     - `VELEZ_MENTOR_VISION_ENABLED=true`
     - `VELEZ_MENTOR_VISION_API_KEY=<masked secret>`
     - `VELEZ_MENTOR_VISION_BASE_URL=https://api.openai.com/v1`
     - `VELEZ_MENTOR_VISION_MODEL=gpt-4o-mini`

3. Autopsy Backfill
   - API: `POST /api/mentor/autopsies/backfill?limit=100`
   - Scans terminal journal trade outcomes and creates missing post-trade autopsies.
   - Automatic future autopsies still run after Alpaca confirms a position has gone flat.

4. Mentor Confidence Meter
   - Included in weekly/today Mentor reports and chart observations.
   - Scores evidence depth from chart bars, quote access, broker position read access, journal context, setup scan completion, and optional image vision.

5. No-trade Coach
   - API: `GET /api/mentor/no-trade?limit=120`
   - Summarizes blocked, rejected, ignored, or guardrail-driven decisions and gives a stand-down question before overriding a no-trade.

6. Setup Watch Mode
   - API: `POST /api/mentor/setup-watch`
   - Watches the selected symbol/timeframe for Velez-qualified structure using connected bars and scanner logic.
   - Returns states such as `watching_no_setup`, `qualified_setup_detected`, or `source_blocked`.

7. Tradier Diagnostics
   - API: `GET /api/mentor/tradier/diagnostics?symbol=SPY&timeframe=5Min`
   - Checks token presence, public base host, interval mapping, reachability, and bar row count without returning credentials.

## Intelligence engines

The Mentor tab now includes a Mentor Intelligence Lab with five additional engines:

1. P/L Attribution Engine
   - API: `GET /api/mentor/pnl-attribution?days=30&limit=200`
   - Buckets closed outcomes into setup quality, risk sizing, exit/stop, slippage/fill, regime/catalyst, no-trade violation, acceptable loss, or positive edge.

2. Strategy Drift Detector
   - API: `GET /api/mentor/strategy-drift?recent_days=30&baseline_days=60`
   - Compares current bot behavior against baseline behavior: frequency, average size, stop distance, planned risk, blocked rate, top symbol, and setup mix.

3. Market Regime + Catalyst Guardrail
   - API: `GET /api/mentor/regime-catalyst?symbol=SPY&timeframe=5Min`
   - Uses connected chart bars and loaded calendar events/earnings to label regime/catalyst risk.

4. Cross-Bot Risk Mirror
   - API: `GET /api/mentor/cross-bot-risk`
   - Reads Velez broker positions and optional external bot risk sources. Configure external sources through `bull_mentor.cross_bot_sources` or `VELEZ_CROSS_BOT_RISK_SOURCES`.
   - If Bull Pilot is not configured as a source, the mirror reports Velez-only instead of inventing cross-bot exposure.

5. Mentor Replay Lab
   - API: `GET /api/mentor/replay-lab?alert_ref=<journal-ref>`
   - Replays a linked trade candle by candle and identifies the first hard invalidation candle when entry/stop evidence is available.

## Safe enhancement lab

The Mentor tab also includes seven safe enhancement tools. Items 3 and 4 are intentionally read-only so they do not conflict with the existing guardrails.

1. Daily Root-Cause Brief
   - API: `GET /api/mentor/daily-root-cause`
   - Combines P/L attribution, drift, no-trade friction, source health, and cross-bot exposure into one first-review action.

2. Trade Quality Heatmap
   - API: `GET /api/mentor/trade-quality-heatmap?days=90`
   - Grades symbol/setup/cause buckets as `elite`, `solid`, `leaky_winner`, `avoid`, or `thin_sample`.

3. Do Not Touch Guardrail Report
   - API: `GET /api/mentor/guardrail-do-not-touch`
   - Advisory/read-only. Lists guardrails Mentor recommends keeping fixed. It does not edit config, loosen risk, submit orders, or approve anything.

4. Broker/Data Reconciliation Score
   - API: `GET /api/mentor/broker-reconciliation`
   - Advisory/read-only. Scores broker positions, lifecycle snapshot, pending approvals, and local claim linkage. It does not repair, cancel, close, or submit broker orders.

5. Bot-to-Bot Parity Matrix
   - API: `GET /api/mentor/bot-parity`
   - Compares Velez Mentor capabilities against configured Bull Pilot evidence sources without inventing external state.

6. What Changed Since Last Good Week
   - API: `GET /api/mentor/last-good-week-delta?lookback_days=180`
   - Compares the latest trading week against the most recent positive week with enough closed trades.

7. Mentor Drill Scheduler
   - API: `GET /api/mentor/drill-scheduler`
   - Optional create action: `POST /api/mentor/drill-scheduler`
   - Recommends a daily drill from the highest-priority root cause. The POST creates a Mentor drill only; it does not affect trading execution.

## Winston Velez Principles Pack

Winston receives a separate read-only Velez strategy reference pack.

- API: `GET /api/winston/velez-principles`
- Included in normal Winston LLM context as `velez_principles_pack`.
- Included in the Strategy Library/bookshelf room-awareness object as `winston_velez_principles_pack`.
- Covers core Velez setup cards, active strategy play IDs, no-chase rules, confluence rules, lower-timeframe filters, risk/sizing gates, portfolio protection, and never-violate principles.
- Rule-based Winston routes direct strategy/rulebook questions into this pack without requiring an LLM.

Role boundary:

- Winston explains strategy rules, summarizes why a setup passed or failed, reads strategy context, and routes coaching questions.
- Bull Mentor owns coaching, scorecards, drills, recurring mistake patterns, P/L attribution, and trader-development diagnosis.

Safety contract:

- The pack is read-only and advisory-only.
- It cannot approve, submit, cancel, repair, close, or modify broker orders.
- It cannot change guardrails, risk settings, strategy thresholds, or watchlist configuration.

## Winston Mentor Context Pack

Winston now receives a compact read-only context pack for the Safe Enhancement Lab.

- Included in Mentor reports as `winston_mentor_context_pack`.
- Included in normal Winston LLM context as `mentor_context_pack`.
- Included in the Mentor room-awareness object.
- Included in Mentor voice briefing payloads and summarized into the spoken memo.
- Rule-based Winston routes direct questions about root cause, heatmap, do-not-touch guardrails, reconciliation, bot parity, last good week, and drill scheduler into Mentor without requiring an LLM.

Safety contract:

- The pack is read-only and advisory-only.
- It cannot approve, submit, cancel, repair, close, or modify broker orders.
- It cannot weaken guardrails or change risk settings.
- Winston should use one or two relevant tool summaries by default and only give the full breakdown when asked.

## Dashboard

Open the Mentor tab. The new cards appear in this order:

- Evidence confidence
- Mentor intelligence lab
- Mentor safe enhancement lab
- No-trade Coach
- Chart Source Health
- Setup Watch Mode
- TradingView eyes-on
- Post-trade autopsies with Backfill autopsies
