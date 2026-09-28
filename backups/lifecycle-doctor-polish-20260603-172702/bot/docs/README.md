# Narrow-to-Wide Trading Bot (Educational)

**Disclaimer:** This project is for educational and research use only. It is not financial advice. Trading involves substantial risk of loss. Use at your own risk.

## Overview
This project implements an Oliver Velez–inspired “Narrow to Wide” state machine with SMA(20)/SMA(200) regime detection, ATR-based risk controls, and optional EMA(9) power-move confirmation. It supports backtesting and a paper-trade replay mode with a broker adapter stub for live integrations.

## Quick Start

### 1) Create a virtual environment and install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Run a backtest

```bash
python bot/main.py backtest --symbols SPY --start 2024-01-01 --end 2024-01-10 --tf 1m
```

### 2b) Launch the desktop UI

```bash
python bot/gui.py
```

### 3) Paper trade replay

```bash
python bot/main.py trade --mode paper --start 2024-01-01 --end 2024-01-10 --tf 1m
```

## Config
Edit `bot/config.yaml` to adjust strategy, risk, broker, and symbol settings.

Key sections:
- `strategy`: indicator windows, narrow/wide thresholds, breakouts, exits
- `risk`: risk per trade, leverage, max daily loss, circuit breaker
- `broker`: slippage and commissions for backtests
- `symbols`: data source per symbol (YFinance or CSV)

## Data Notes
- **YFinance minute data is limited** (typically last 7 days for 1m bars). For longer tests, use CSV.
- Futures data is expected via CSV. ES sample path is `bot/data/ES.csv`.
- Sessions: `rth` filters to 09:30–16:00 Eastern for equities.

## Output Format Example

```
Backtest Metrics
 total_pnl: 1234.56
 ending_equity: 101234.56
 win_rate: 0.48
 expectancy: 12.34
 max_drawdown: 0.08
 cagr: 0.12
 sharpe: 0.75
Trades: 42
```

## Extending
- Add alerts (Telegram) by emitting messages in `core/utils.py` log hooks.
- Add a real broker by implementing `brokers/base.py` (e.g., IBKR via `ib_insync`).

## TradingView + Alpaca Paper Webhook

The Velez institutional strategy package is implemented in `bot/core/velez_strategy.py` and documented in `bot/docs/velez_core_strategies.md`.

Run the webhook in proposal mode:

```bash
export VELEZ_WEBHOOK_SECRET="long-random-token"
export VELEZ_EXECUTE_ORDERS=false
python3 -m bot.main --config bot/config.yaml webhook --host 127.0.0.1 --port 8080
```

Arm paper order submission only when ready:

```bash
export VELEZ_EXECUTE_ORDERS=true
python3 -m bot.main --config bot/config.yaml webhook --host 127.0.0.1 --port 8080 --execute
```

See `bot/docs/TRADINGVIEW_ALPACA.md` for TradingView webhook options and the included Pine Script.

## Trading Bull Desk Dashboard

The webhook server also serves the visual command room at:

```text
http://127.0.0.1:8080/dashboard
```

On the VPS, use:

```text
https://velezbot.72.62.169.3.nip.io/dashboard
```

The dashboard shows broker status, execution mode, open positions, risk limits, Velez 1-to-4 lot sizing, bot health, persistent TradingView decisions, confidence receipts, trade review, replay mode, risk replay, live lifecycle reconciliation, active-trade management readbacks, hybrid VPS scanner status, alert coverage, dry-run webhook testing, VPS hardening/latency checks, daily close reports, the daily mission card, event countdowns, chart capture, the live calendar panel, watchlist controls, the Apple Music iPod panel, and the Winston desk-phone panel without exposing Alpaca keys, webhook secrets, Apple private key material, or approval tokens. See `bot/docs/DASHBOARD_V5.md`.

When the dashboard is reachable beyond localhost, enable HTTP Basic auth:

```bash
export VELEZ_DASHBOARD_AUTH_ENABLED=true
export VELEZ_DASHBOARD_USERNAME="desk"
export VELEZ_DASHBOARD_PASSWORD="long-random-dashboard-password"
```

This protects `/dashboard`, `/dashboard/assets`, and `/api/*`. `/health` stays public for uptime checks, and TradingView webhooks continue to use the separate webhook secret.

## Hybrid VPS Scanner

V6.21 adds an always-on scanner inside the VPS webhook service. TradingView webhooks remain active, but the VPS also scans the enabled Trading Bull Desk watchlist with Alpaca market data, warms up the same Oliver Velez strategy brain, and then acts only on newly closed bars. Scanner signals are routed through the same sizing, risk, stop, max-position, paper-endpoint, and order-submission guardrails as TradingView alerts.

Key config lives under `scanner:` in `bot/config.yaml`. The live default scans supported equity/crypto watchlist lanes on `1Min` bars every 60 seconds. Unsupported assets such as futures are skipped until a futures data source is wired.

The calendar panel uses Alpaca for month P/L, open-position mark, and market sessions; Alpha Vantage for watchlist earnings; and free official macro sources from BLS, BEA, Census, NY Fed, and the Federal Reserve.

V6.12 expands the Velez scanner beyond Elephant/180/Tail into Buy/Sell Setups, NRB/Acorn, first color-change add candidates, Fab 4 trap-zone breakouts, Failed New High/Low reversals, and management-plan metadata for profit taking and trailing. V6.13 stabilizes the Command Center watchlist form so the live refresh no longer clears the symbol field while typing. V6.14 refreshes the dashboard brand mark with the new gold-and-blue bull logo. V6.15 adds the opening-gap and time-space brain with `opening_gap_go`, `opening_gap_fade`, and `time_space_breakout`. V6.16 adds alert coverage, dry-run webhook testing, trade review, guarded approval-mode toggling, Winston Morning Call, and VPS hardening helpers. V6.17 upgrades Winston to a hybrid DeepSeek/Ollama brain profile with DeepSeek Flash for phone mode, DeepSeek Pro for Research Mode, DeepSeek thinking controls, and local Ollama fallback. V6.18 adds Winston Deep Research, confidence receipts, Daily Close Report, richer alert coverage checks, risk replay sizing, and VPS uptime/latency probes. V6.19 adds read-only Alpaca lifecycle reconciliation, a trade lifecycle command center, Winston active-trade readbacks, outcome logging, and guardrail alerts for missing stops/orphan positions/pending-order overlap. V6.20 adds Oliver Velez 1-to-4 lot conviction sizing so A+ power setups and 20/200 SMA power locations can scale up while every order still stays inside the configured max risk budget. V6.21 adds the hybrid VPS scanner that watches newly closed Alpaca bars from the desk watchlist alongside TradingView alerts.

## Winston Desk Phone

Click the phone on the desk to call Winston. V6.19 starts with a Morning Call, supports daily briefs with health/readiness/watch-plan context, Research Mode, Deep Research, after-action review context, watchlist/risk/position/lifecycle readbacks, fast deterministic iPod and room-object commands, DeepSeek `deepseek-v4-flash` phone answers, DeepSeek `deepseek-v4-pro` research lanes, local Ollama fallback, Hermes PocketTTS voice output, browser voice fallback, optional browser speech input, guarded paper-order approvals, stabilized watchlist typing in the Command Center, the refreshed Trading Bull logo, and opening-gap/time-space setup readbacks. Approval requires a staged bot proposal, an exact phrase, the browser approval token, paper execution mode, and the existing Alpaca paper guardrails.

Room objects now include the daily mission card, strategy bookshelf, market session clock, market-weather window, risk mood lamp, backtest drawer, and Bull Report prep/review panel in addition to the laptop, journal, calendar, safe, iPod, and Winston phone.

Useful Winston endpoints:

```text
/api/winston/status
/api/winston/brief
/api/winston/message
/api/winston/morning-call
/api/winston/research
/api/winston/deep-research
/api/winston/speech
/api/review/daily
/api/review/close
/api/alerts/coverage
/api/lifecycle/state
/api/lifecycle/reconcile
/api/lifecycle/outcomes
/api/webhook/test
/api/risk/status
/api/orders/pending
/api/bot/health
/api/vps/hardening
/api/vps/latency
/api/journal/recent
/api/journal/review
/api/replay/run
/api/replay/risk
```

Follow-up ideas and next-build notes live in `bot/docs/TODO.md`.
Release discipline lives in `bot/docs/RELEASE_CHECKLIST.md`, VPS/local parity checks live in `bot/docs/VPS_PARITY.md`, and the daily operator flow lives in `bot/docs/MORNING_DESK_RUNBOOK.md`.

## Apple Music iPod Panel

To enable the iPod's Apple Music connection, keep the `.p8` key outside the package and set:

```bash
export APPLE_MUSIC_TEAM_ID="your-10-character-team-id"
export APPLE_MUSIC_KEY_ID="your-media-services-key-id"
export APPLE_MUSIC_PRIVATE_KEY_PATH="/absolute/path/to/AuthKey_KEYID.p8"
export APPLE_MUSIC_TOKEN_TTL_HOURS=12
export APPLE_MUSIC_TOKEN_ORIGINS="https://your-bot-domain.example"
```

Then open the dashboard, click `Music`, and choose `Connect Music`. The browser handles your Apple Music authorization; the bot only serves a short-lived developer token. Once authorized, use the iPod panel to search Apple Music and control browser playback inside Trading Bull Desk.

## Notes: Telegram + Render
- Telegram: add a small notifier in `core/utils.py` that posts to a bot token + chat ID on key events (`signal`, `trade`, `risk_block`). Keep it optional via config/env vars.
- Render: run the bot as a background worker using the `trade` command, store logs to stdout, and mount a persistent disk for CSV data/cache. Use environment variables for secrets (broker keys, Telegram token).

## Build a macOS App (.app)

```bash
./scripts/build_mac_app.sh
```

The app will be created at `dist/NarrowWide.app`.

## Build a macOS Release (App Icon + Installer + DMG)

```bash
./scripts/build_release.sh
```

Outputs:
- `dist/NarrowWide.app`
- `dist/NarrowWide Installer.app` (one‑click installer)
- `dist/NarrowWide.dmg` (drag‑to‑install + installer app)

## Optional: Code Signing + Notarization

Sign the app (requires a Developer ID Application certificate):

```bash
./scripts/sign_mac_app.sh "Developer ID Application: Your Name (TEAMID)"
```

Notarize the DMG (requires Apple ID credentials or a keychain profile):

```bash
# Option A: keychain profile
NOTARY_PROFILE="notarytool-profile" ./scripts/notarize_mac_app.sh

# Option B: credentials
APPLE_ID="you@example.com" APPLE_TEAM_ID="TEAMID" APP_PASSWORD="app-specific-password" ./scripts/notarize_mac_app.sh
```
