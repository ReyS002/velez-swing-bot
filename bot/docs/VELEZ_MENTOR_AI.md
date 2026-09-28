# Velez Mentor AI

Velez Mentor AI is an embedded, advisory-only coaching layer inside the Velez Trading Bot dashboard. It mirrors the Bull Pilot Mentor contract while reading only Velez journal, risk, lifecycle, broker-fill, and market-data evidence.

## Where to find it

- Dashboard: open the room menu and choose `Mentor`.
- Winston: ask for `Velez Mentor`, `coach me`, `my scorecard`, `my drill`, a specific journal alert review, or a live setup/chart read such as `what do you see on this setup?`.
- API:
  - `GET /api/mentor/today`
  - `GET /api/mentor/weekly?days=7`
  - `GET /api/mentor/trade/{alert_ref}`
  - `GET /api/mentor/profile`
  - `POST /api/mentor/profile`
  - `POST /api/mentor/ask`
  - `POST /api/mentor/chart/observe`
  - `POST /api/mentor/drills/build`
  - `POST /api/mentor/drills/{id}`
  - `GET /api/mentor/autopsies`
  - `GET /api/mentor/autopsies/{id}/chart`
  - `GET /api/mentor/briefings/{morning|evening}`
  - `POST /api/mentor/briefings/{morning|evening}/telegram`
  - `POST /api/mentor/operations/run`

## Guardrails

Mentor cannot place, approve, cancel, or modify orders. It cannot change risk settings or weaken guardrails. Optional Winston narration receives a bounded Mentor report, not broker credentials or private account secrets.

Mentor's chart observation is read-only. It can analyze the selected TradingView symbol and timeframe from connected bars, journal context, scanner logic, quotes, positions, and optional browser-capture metadata. For equities, the default source order is Alpaca bars first, Tradier bars second when `TRADIER_ACCESS_TOKEN` is configured, and yfinance last as a free fallback. TradingView embeds are cross-origin iframes, so Mentor does not claim pixel-level vision unless a future explicit vision provider is configured.

## Mentor edge suite

The Mentor room now includes eight named capabilities:

- `Response Governor`: enforces answer mode, personality style, word cap, and no-fluff cleanup across deterministic and LLM replies.
- `Trade Replay Coach`: separates entry facts, location, invalidation, and outcome for selected trades or autopsies.
- `Mistake Fingerprint`: tracks recurring leaks such as weak location, undefined risk, chase behavior, guardrail friction, and execution-measurement gaps.
- `Shadow Book`: tracks skipped, rejected, and ignored setups so missed winners and saved losers can be reviewed when forward evidence exists.
- `Pre-Trade Challenge`: creates one sharp stand-down question before risky or ambiguous setups.
- `Institutional Lens`: checks arrival price, participation caps, child-order schedule, slippage, prop uniformity, and exposure discipline.
- `One-Tap Drill Builder`: converts the current weakest dimension into a saved active drill.
- `Personality Dial`: supports Leo concise, concise, detailed, Socratic, Winston analyst, prop risk officer, and Velez drill sergeant modes.

## Evidence used

Mentor reads:

- Velez alert decisions and confidence receipts
- Trade outcomes and lifecycle close records
- Broker execution metadata already stored in the local journal
- Optional connected OHLC bars for post-trade entry charts
- Connected OHLC bars for live/post-market TradingView setup observations, using Alpaca -> Tradier -> yfinance for equities
- Current risk, lifecycle, daily brief, and market-regime context for voice memo scripts

Closed Alpaca paper position transitions can create post-trade autopsies with a setup review, risk review, Mentor lesson, and local SVG chart when source bars are available.
