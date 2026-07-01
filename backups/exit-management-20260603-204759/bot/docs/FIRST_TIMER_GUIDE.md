# Velez Trading Bot: First-Timer Guide

Educational and paper-trading use only. This bot is designed to start safe: it proposes orders by default and only submits Alpaca paper orders when you deliberately arm it.

## What The Bot Does

The bot listens for TradingView alerts, checks them against Oliver Velez-style institutional price-action rules, sizes each trade by risk, and can send the order to Alpaca paper trading.

It focuses on:

- Elephant Bars
- Bull 180 and Bear 180 reversals
- Bottoming Tail and Topping Tail reversals
- Opening Gap Go, Opening Gap Fade, and Time + Space breakouts
- 20 SMA and 200 SMA location filters
- Fixed dollar risk sizing
- Stop-loss protection
- No-chase limit-entry logic

## The Simple Explanation

Tell someone this:

> TradingView watches the chart. When it sees a setup, it sends a webhook alert to the bot. The bot checks the setup, calculates the position size from the entry and stop, and then either proposes the order or sends it to Alpaca paper trading.

The VPS scanner is the backup/second lane. It watches the enabled Trading Bull Desk watchlist directly from the VPS, warms up on old candles without trading them, then checks newly closed candles with the same Oliver Velez brain. In plain English: TradingView can still shout alerts, but the VPS can also look for setups by itself.

## Where The Bot Lives

Main folder:

```text
/Users/rey/Documents/New project/bot
```

Main command:

```text
/Users/rey/Documents/New project/bot/main.py
```

Strategy file:

```text
/Users/rey/Documents/New project/bot/core/velez_strategy.py
```

TradingView Pine Script:

```text
/Users/rey/Documents/New project/bot/tradingview/velez_core_alerts.pine
```

## How To Start The Bot Safely

Open Terminal:

```bash
cd "/Users/rey/Documents/New project"
```

Start in proposal mode:

```bash
export VELEZ_WEBHOOK_SECRET="your-secret-token"
export VELEZ_EXECUTE_ORDERS=false

python3 -m bot.main --config bot/config.yaml webhook --host 127.0.0.1 --port 8080
```

Proposal mode means the bot is awake, but it will not submit orders.

Check health:

```bash
curl -s http://127.0.0.1:8080/health
```

Open the visual dashboard:

```text
http://127.0.0.1:8080/dashboard
```

On the VPS, the dashboard is:

```text
https://velezbot.72.62.169.3.nip.io/dashboard
```

## How To Use The Calendar

Click the wall calendar in the room, or open `Calendar` from the left edge menu.

The calendar shows:

- Month P/L from Alpaca portfolio history
- Open-position unrealized P/L from Alpaca positions
- TradingView alert count from the bot session journal
- Market session status from Alpaca's market calendar
- Watchlist earnings from Alpha Vantage
- Macro events from free official sources such as BLS, BEA, Census, NY Fed, and the Federal Reserve

For earnings, set:

```bash
export ALPHA_VANTAGE_API_KEY="your-alpha-vantage-key"
```

The macro feeds do not need paid Trading Economics access. They use public government calendar pages and fail quietly if one source is temporarily unavailable.

## How To Use The Laptop Watchlist

Click the laptop on the desk, or open `Command` from the left edge menu.

Use the watchlist form to add or remove symbols. The bot stores those edits in its local journal database, so the dashboard and calendar remember them after a restart. New symbols are used for dashboard context and earnings checks; TradingView still needs to send alerts for any symbol you want the bot to evaluate.

The laptop also has `Bot health`, `Replay mode`, `Alert coverage`, `Risk command center`, `Trade lifecycle command center`, and `VPS hardening`.

- `Bot health` tells you whether the VPS/API, Alpaca paper connection, paper endpoint, TradingView webhook listener, journal database, Winston brain, and Winston voice are ready.
- `Replay mode` runs sample candle sequences through the Velez rules without sending anything to Alpaca. Use it to confirm the scanner is detecting setups before trusting more automation.
- `Alert coverage` lets you mark which symbols are in your TradingView Watchlist Alert group, then shows the last alert the bot actually received for each watchlist symbol.
- `Test webhook pipe` sends a dry-run diagnostic through the bot's webhook/risk path. It records a diagnostic journal item but never stages or submits an order.
- `Risk command center` shows paper execution state, max risk, daily loss cap, max positions, and the approval-mode toggle. Changing approval mode requires the local approval token.
- `Lot flow` shows the Oliver Velez 1-to-4 lot conviction ladder. One lot is a starter risk unit; four lots is full configured risk, not four times the max risk.
- `Trade lifecycle command center` reads the live Alpaca paper account, matches open positions to the bot journal, checks open broker orders/stops/fills, shows current R multiple, and flags guardrails like missing stops or orphan positions. It is read-only; it does not move stops, close trades, or submit exits.
- `VPS hardening` shows restart, database, data directory, backup, and public-health helper status.

## How To Read The Trade Journal

Click the journal on the desk, or open `Journal` from the left edge menu.

Each journal card is a saved TradingView decision. It shows the setup, status, grade, readback, entry, stop, estimated risk, and alert reference. A `proposed` or `submitted` card means the bot found an actionable setup. A `rejected`, `ignored`, or `error` card tells you which guardrail blocked it.

Plain-English version: the journal is the bot's memory. It lets you review what the bot saw, what it decided, and why.

Click `Review` on any journal card to inspect rule checks, sizing, chart context, and what happened next for that symbol. Click `Replay setup` to run the matching sample scenario without sending an order.

The V6.19 `Lifecycle outcomes` lane records active-trade milestones such as open-position reconciliation, 1R reached, 2R reached, and lifecycle guardrail alerts. Plain-English version: alerts explain why the bot wanted a trade; lifecycle explains what the live paper account looks like after the trade exists.

## How To Use The Calendar Timeline

Click the calendar on the desk, or open `Calendar` from the left edge menu.

The top metrics still show month P/L, open-position mark, alert count, and event count. The new timeline combines market sessions, macro events, earnings, and journal activity into one upcoming desk lane.

## How To Use Winston Research Mode

Click the phone, start a call, type a research topic, then click `Research`.

Examples:

```text
SPY prep for tomorrow
QQQ earnings and macro risks
Daily prep for the watchlist
```

Research Mode uses the bot's current desk state, calendar, journal, watchlist, and Alpha Vantage context when available. It is prep context only, not financial advice.

## How Guarded Paper Approval Works

When the bot is in proposal mode, a qualified TradingView setup stages a pending paper order instead of submitting it. Winston can read back the symbol, side, quantity, entry, stop, and exact approval phrase.

If you want the VPS to hold every qualified alert for approval even while paper execution is armed, set:

```text
VELEZ_REQUIRE_ORDER_APPROVAL=true
```

To approve from the phone:

1. Enter the approval token in the phone panel.
2. Read the staged order details.
3. Say or type the exact phrase, for example:

```text
APPROVE PAPER ORDER ABCD1234
```

The bot then checks the token, exact phrase, paper Alpaca endpoint, and execution guardrails before submitting. Without the token and exact phrase, Winston will only discuss the order; it will not submit it.

## How Lot Sizing Works

The bot sizes trades in two steps:

1. It grades the setup into 1, 2, 3, or 4 lots.
2. It converts that lot risk budget into actual shares/contracts using entry, stop, contract multiplier, max quantity, and leverage guardrails.

Plain-English version: lots are conviction, not recklessness. A normal qualified setup may use 1 lot. A clean Elephant Bar, 180, Tail Bar, Opening Gap Go, or Time + Space Breakout can start around 2 lots. If that A+ event happens at a position of power, especially the 20 SMA or 200 SMA, it can step to 3 lots. A rare clean power candle at a major location can reach 4 lots, which equals the configured max risk budget.

Defensive caps still apply. Missing location caps at 1 lot, chased entries are capped, wide stops are capped, and continuation trades far extended from the 20 SMA are kept defensive unless they are reversal/contrarian plays.

## How To Use The Apple Music iPod

The desk iPod connects to Apple Music through a secure MusicKit bridge. The Apple private key stays on the server, not in the browser.

On the dashboard:

1. Click `Music` on the left toolbar, or click the iPod on the desk.
2. Click `Connect Music`.
3. Sign in or approve Apple Music when the browser asks.
4. Search for a song, album, or playlist inside the iPod panel.
5. Press the play button on a result to queue it inside Trading Bull Desk.
6. Use the mini player controls for play/pause, previous, next, and now-playing progress.
7. Use `Open Player` or `Focus Search` when you want the full Apple Music web player.

After Apple Music is connected in the browser, Winston can also route simple iPod commands from the phone, such as `play Sade on the iPod`, `pause music`, `next track`, `turn the volume down`, or `what is playing`. If the browser is not authorized yet, Winston will search/show the result and ask for one manual `Connect Music` click before playback.

For a new setup, these environment variables must exist before starting the bot:

```bash
export APPLE_MUSIC_TEAM_ID="your-10-character-team-id"
export APPLE_MUSIC_KEY_ID="your-media-services-key-id"
export APPLE_MUSIC_PRIVATE_KEY_PATH="/absolute/path/to/AuthKey_KEYID.p8"
export APPLE_MUSIC_TOKEN_TTL_HOURS=12
export APPLE_MUSIC_TOKEN_ORIGINS="https://your-bot-domain.example"
```

## How To Use The Winston Phone

The desk phone is the voice-command surface for Winston. It does not submit trades by voice; it reads desk state, uses DeepSeek Flash for quick phone answers, uses DeepSeek Pro for Research and Deep Research, keeps the VPS Ollama brain as a fallback, can control the Apple Music iPod after browser authorization, can open room objects such as the bookshelf, clock, lamp, drawer, notes, and window, can speak through Hermes PocketTTS, and keeps trade approval guarded.

On the dashboard:

1. Click the phone on the desk, or click `Phone` on the left toolbar.
2. Click `Call Winston`. Winston starts the Morning Call automatically.
3. Click `Daily Brief` for the shorter broker, watchlist, position, risk, and latest-alert summary.
4. Click `Research` for a quick prep note, or `Deep Research` for a deeper memo using more of the desk context.
5. Use the text box to ask for the watchlist, positions, active trade stops/R multiple, risk, trade approval status, or simple iPod commands.
6. Click `Speak` if your browser supports speech recognition.
7. Winston speaks back through Hermes PocketTTS when the server voice is configured, or through the browser voice fallback.

Plain-English version: Winston is now the phone assistant inside the desk. The bot can answer from its own dashboard state, read active paper-trade lifecycle details, use a local/remote AI model for open-ended questions, and speak back in the configured Hermes voice. It still will not place trades just because someone says "buy" or "approve"; it only reads status and keeps trading actions behind a separate guarded approval flow.

## How To Read V6.21 Receipts And Lifecycle

Every saved alert gets a confidence receipt. In plain English, it is a checklist showing whether the alert had the basics: a valid location, entry, stop, size, no chase flag, timeframe, and compatible payload. The close report summarizes the day, alert coverage, risk mode, next-session watch plan, and anything that needs attention before leaving the VPS running.

The V6.19 lifecycle panel is the after-entry monitor. It checks Alpaca paper positions, open orders, and recent fills, then compares them to the journal. Ask Winston "what are my active positions and stops?" for a spoken readback.

## How To Use The Room Objects

Click objects directly in the office, or reveal the left room menu. The bookshelf opens the strategy library, the clock shows market sessions, the window shows market weather, the lamp shows risk mood, the drawer opens replay/backtest mode, and sticky notes store your daily manual reminder in this browser.

## How To Connect TradingView

1. Open TradingView.
2. Add the Pine Script from:

```text
bot/tradingview/velez_core_alerts.pine
```

3. Create an alert.
4. Use this alert condition:

```text
Any alert() function call
```

5. Use a webhook URL like:

```text
https://YOUR_PUBLIC_URL/webhook/tradingview/YOUR_SECRET_TOKEN
```

TradingView cannot call `localhost` directly. Use a public deployment, ngrok, or Cloudflare Tunnel.

## How To Paper Trade With Alpaca

Only after testing proposal mode, arm Alpaca paper execution:

```bash
export APCA_API_KEY_ID="your-alpaca-paper-key"
export APCA_API_SECRET_KEY="your-alpaca-paper-secret"
export APCA_API_BASE_URL="https://paper-api.alpaca.markets"
export VELEZ_WEBHOOK_SECRET="your-secret-token"
export VELEZ_EXECUTE_ORDERS=true

python3 -m bot.main --config bot/config.yaml webhook --host 127.0.0.1 --port 8080 --execute
```

The bot requires both:

- `VELEZ_EXECUTE_ORDERS=true`
- `--execute`

Without both, it will only propose orders.

## Safety Rules

The bot blocks execution when:

- the webhook secret is wrong,
- Alpaca credentials are missing,
- the Alpaca endpoint is not paper trading,
- the stop price is invalid,
- the stop distance is too large,
- max open positions is reached,
- daily loss or consecutive-loss guardrails are tripped,
- the setup is missing proper Velez location.

## How To Stop The Bot

In the Terminal window running the bot, press:

```text
Control + C
```

## Best First Demo

1. Start the bot in proposal mode.
2. Trigger one TradingView alert.
3. Confirm the bot returns an order proposal.
4. Confirm the stop price and quantity make sense.
5. Only then turn on Alpaca paper execution.

## Files Included In The Package

- Bot source code
- Velez strategy implementation
- TradingView webhook server
- Alpaca paper broker adapter
- TradingView Pine Script
- Config file
- Environment variable example
- First-timer guide
- TradingView/Alpaca connection guide
- Safety guide
- Trading Bull Desk dashboard V6.21 guide
- Tests
- Python requirements
