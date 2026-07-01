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

The dashboard shows broker status, execution mode, open positions, risk limits, bot health, persistent TradingView decisions, replay mode, the daily mission card, event countdowns, chart capture, the live calendar panel, watchlist controls, the Apple Music iPod panel, and the Winston desk-phone panel without exposing Alpaca keys, webhook secrets, Apple private key material, or approval tokens. See `bot/docs/DASHBOARD_V5.md`.

The calendar panel uses Alpaca for month P/L, open-position mark, and market sessions; Alpha Vantage for watchlist earnings; and free official macro sources from BLS, BEA, Census, NY Fed, and the Federal Reserve.

## Winston Desk Phone

Click the phone on the desk to call Winston. V6.6 supports daily briefs with health/readiness/watch-plan context, Research Mode, after-action review context, watchlist/risk/position readbacks, fast deterministic iPod and room-object commands, Ollama `qwen3:1.7b` phone answers on the VPS, Ollama `qwen3.5:2b` Research Mode, Hermes PocketTTS voice output, browser voice fallback, optional browser speech input, and guarded paper-order approvals. Approval requires a staged bot proposal, an exact phrase, the browser approval token, paper execution mode, and the existing Alpaca paper guardrails.

Room objects now include the daily mission card, strategy bookshelf, market session clock, market-weather window, risk mood lamp, backtest drawer, and sticky-note prep/review panel in addition to the laptop, journal, calendar, safe, iPod, and Winston phone.

Useful Winston endpoints:

```text
/api/winston/status
/api/winston/brief
/api/winston/message
/api/winston/research
/api/winston/speech
/api/review/daily
/api/orders/pending
/api/bot/health
/api/journal/recent
/api/replay/run
```

Follow-up ideas and next-build notes live in `bot/docs/TODO.md`.

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
