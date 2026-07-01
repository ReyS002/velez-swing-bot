# Trading Bull Desk Dashboard V6.5

Dashboard V6.5 keeps the Candidate C room as the main visual stage, keeps the front end named Trading Bull Desk, and hides the side controls so more of the room is visible. The monitor attempts to load TradingView's official Advanced Chart widget, while the local canvas chart remains underneath as a fallback if the external widget is blocked or slow. The iPod works as an in-desk Apple Music mini player through MusicKit JS, the desk phone supports Winston daily briefs, fast iPod commands, room-object commands, Research Mode, Hermes PocketTTS voice, and guarded paper-order approvals, and the calendar pulls live broker, earnings, macro, and journal data.

## V6.5 Room Object System

- Added clickable room-object panels for the bookshelf, desk clock, window, lamp, drawer, and sticky notes
- Bookshelf opens a compact Velez strategy library with Elephant Bar, 180, Tail, Pyramiding, and No-Chasing cards
- Clock shows New York session status and caution windows
- Window shows market-weather context from bot health, calendar events, watchlist, and positions
- Lamp shows a risk mood light derived from health, broker, execution, and open exposure
- Drawer opens replay/backtest mode and recent replay results
- Sticky notes show Winston prep lines and a browser-local manual note
- Winston can open the new objects with phrases such as `open the strategy library`, `open the clock`, `open the lamp`, or `open sticky notes`

## URL

Local:

```text
http://127.0.0.1:8080/dashboard
```

VPS:

```text
https://velezbot.72.62.169.3.nip.io/dashboard
```

## V5.7 Cleanup

- Removed the old upper-right Winston/Jarvis placeholder hotspot and side-menu item
- Kept the desk phone as the single Winston command surface
- Bumped dashboard assets to `v=5.7` for cache refresh

## V5.8 Calendar Feeds

- Added `/api/calendar/month`
- Added Alpaca portfolio-history P/L, open-position unrealized mark, and market-session calendar checks
- Added session-journal alert counts from the bot's recent TradingView decisions
- Added Alpha Vantage watchlist earnings from `EARNINGS_CALENDAR`
- Added free official macro calendar sources: BLS iCal, BEA release schedule, Census economic indicators, New York Fed economic calendar, and Federal Reserve FOMC calendar
- Added cache and timeout controls so a slow agency feed cannot freeze the dashboard

Environment variables:

```text
ALPHA_VANTAGE_API_KEY=your-alpha-vantage-key
CALENDAR_FEED_TIMEOUT_SECONDS=8
CALENDAR_FEED_CACHE_SECONDS=21600
CALENDAR_EVENT_LOOKAHEAD_DAYS=45
CALENDAR_MACRO_FEEDS_ENABLED=true
BLS_CALENDAR_ICS_URL=https://www.bls.gov/schedule/news_release/bls.ics
BEA_CALENDAR_URL=https://www.bea.gov/news/schedule/full
CENSUS_CALENDAR_URL=https://www.census.gov/economic-indicators/calendar-listview.html
NYFED_CALENDAR_URL=https://www.newyorkfed.org/research/national_economy/nationalecon_cal.html
FOMC_CALENDAR_URL=https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
```

## V6.6 Mission, Review, And Room-State Layer

- Added a Daily Mission room object and left-menu item for session focus, event risk, risk mood, approvals, review, chart capture status, and watchlist heat
- Added browser-side chart capture from the desk chart canvas plus TradingView chart-context links on journal cards
- Added `/api/review/daily` for Winston after-action review summaries from the persistent journal
- Added market event countdown cards to Mission, Calendar, and Clock
- Added the Safe Approval Inbox, using the existing exact phrase plus browser approval-token guardrail before any paper submission
- Added object glow states for pending approvals, event risk, live Winston/iPod activity, saved captures, and end-of-day lock state
- Added watchlist heat strips to Trading Screen, Mission, Laptop, and Window
- Added the Notes End-of-Day Lock Ritual, stored locally in the browser as a desk closeout snapshot

## V6.4 Winston iPod Playback Fix

- Bumped dashboard assets to `v=6.4` so browsers load the latest action-handler JavaScript
- Winston iPod commands now open the Music panel, search Apple Music immediately, and show the result instead of silently waiting
- Voice-triggered playback no longer tries to launch MusicKit authorization from a non-user browser callback; if needed, Winston asks for one manual `Connect Music` click first

## V6.2 Fast Winston + iPod Router

- Added a deterministic Winston command router before the LLM for fast commands like `play Sade on the iPod`, `pause music`, `next track`, `turn volume down`, `what is playing`, and `open the journal`
- Added browser-side execution of Winston actions so Apple Music commands search, queue, play, pause, skip, and adjust volume through the existing MusicKit session
- Smoke-tested VPS Ollama models and selected `qwen3:1.7b` for phone mode because it balanced speed and safer desk readbacks better than the 1B models
- Kept Winston Research Mode on `qwen3.5:2b` for deeper notes while the phone line stays quick

## V6.1 Desk Operations

- Added `/api/bot/health` and a laptop health panel for VPS/API, public URL, Alpaca paper, paper endpoint, execution mode, webhook last-alert age, journal database, calendar feeds, Winston brain, Winston voice, and positions
- Added `/api/journal/recent` and upgraded the journal panel with setup grades, readback lines, risk/unit, estimated risk dollars, target R, setup counts, and replay history
- Added `/api/replay/run` and `/api/replay/latest` for safe Velez replay mode; replay scans candles and never submits broker orders
- Added a combined calendar timeline so sessions, macro events, earnings, and journal activity appear in one upcoming desk lane
- Upgraded `/api/brief/daily` and Winston daily brief output with bot health, readiness, watch plan, calendar focus, risk readback, and approval status

## V6.0 Desk Brain

- Added persistent SQLite journal storage for TradingView decisions, research notes, watchlist edits, and staged approval orders
- Added `/api/brief/daily` and upgraded `/api/winston/brief` with P/L, session, macro, earnings, recent-alert, risk, and pending-order context
- Added watchlist management from the laptop panel with `/api/watchlist`
- Added Winston Research Mode at `/api/winston/research`; it uses Alpha Vantage context when a symbol is available and the configured local LLM when reachable
- Added guarded pending paper-order approvals at `/api/orders/pending` and `/api/orders/pending/{id}/approve`
- Added an approval-token field in the phone panel; the token stays in that browser's local storage and is required in addition to the exact approval phrase

Persistence and approval env:

```text
VELEZ_DATA_DIR=/app/data
VELEZ_APPROVAL_API_TOKEN=replace-with-a-separate-local-approval-token
VELEZ_AUTO_STAGE_PROPOSED_ORDERS=true
VELEZ_REQUIRE_ORDER_APPROVAL=false
VELEZ_APPROVAL_TTL_MINUTES=30
```

The approval flow is intentionally narrow. A TradingView alert must first create a valid proposed order with symbol, side, quantity, entry, stop, and risk. Winston can read it back. The user must then provide the exact phrase, such as `APPROVE PAPER ORDER ABCD1234`, and the browser approval token. The bot still checks that execution is armed and the Alpaca endpoint is paper trading before submitting.

When `VELEZ_REQUIRE_ORDER_APPROVAL=true`, even an armed paper-execution stack holds qualified alerts as pending approvals instead of auto-submitting them. Leave it `false` to keep the current automatic paper execution behavior.

## V5.6 Upgrades

- Added `/api/winston/status` so the phone shows the active brain and voice providers
- Added optional Ollama/Hermes local LLM support for Winston chat
- Added optional Hermes PocketTTS server voice via `/api/winston/speech`
- Added browser speech fallback when server TTS is unavailable or muted
- Added runtime guardrails so Winston voice chat cannot submit, approve, cancel, buy, sell, or close trades directly
- Added provider metadata in the Winston phone panel: `Brain` and `Voice`
- Kept rule-based Winston responses as the safe fallback when no LLM is configured

## V5.5 Upgrades

- Replaced the `TB` text mark with the Trading Bull logo image
- Replaced the diffuser with a phone in the day and night room plates
- Added an invisible phone hotspot that opens the Winston phone line
- Added Winston call controls: call/end, mute, speak, daily brief, and typed prompts
- Added server endpoints for Winston daily briefs and guarded prompt responses
- Renamed the front interface to Trading Bull Desk
- Changed the left object menu to an edge-reveal drawer
- Changed the right detail panel to stay hidden until an object is selected
- Fixed MusicKit authorization by configuring MusicKit first, then using `MusicKit.getInstance()` before calling `authorize()`
- Preloads MusicKit after the dashboard confirms Apple Music is configured, so the user click can go straight to authorization
- Added an in-desk Apple Music mini player with album art, play/pause, previous/next, progress, and now-playing state
- Added Apple Music catalog search for songs, albums, and playlists from the iPod panel
- Lets a selected search result authorize, queue, and play inside Trading Bull Desk instead of only opening Apple Music externally
- Embedded TradingView Advanced Chart widget into the physical monitor
- Added SPY and QQQ chart buttons in the Trading Screen panel
- Kept the existing Velez canvas chart as an automatic fallback
- Added a server-side Apple Music developer-token bridge
- Added MusicKit JS authorization from the iPod panel
- Kept Apple Music web and focus-search shortcuts
- Preserved the V4.6 day/night command room pair and invisible hotspots

## Winston Phone Line

Click the phone on the desk, or choose `Phone` from the edge menu. The phone panel can read a daily desk brief, watchlist status, open-position summary, risk settings, and guarded paper-trade approval status.

```text
/api/winston/brief
/api/winston/message
/api/winston/status
/api/winston/speech
```

Voice output uses Hermes PocketTTS when these environment variables are configured, then falls back to the browser's speech synthesis. Voice input uses the browser speech-recognition API when available; otherwise, type into the phone prompt. Trade approval is intentionally guarded: Winston can discuss structure and read back pending paper orders, but the V6.2 phone flow still does not submit trades by voice alone.

```text
WINSTON_LLM_PROVIDER=ollama
WINSTON_LLM_BASE_URL=http://127.0.0.1:11434
WINSTON_LLM_MODEL=qwen3:1.7b
WINSTON_LLM_THINK=false
WINSTON_RESEARCH_LLM_MODEL=qwen3.5:2b
WINSTON_RESEARCH_THINK=false
WINSTON_RESEARCH_MAX_TOKENS=320
WINSTON_RESEARCH_CONTEXT_CHARS=7000
WINSTON_RESEARCH_TIMEOUT_SECONDS=120
WINSTON_TTS_PROVIDER=pockettts
WINSTON_TTS_BASE_URL=http://127.0.0.1:8018/v1
WINSTON_TTS_API_KEY=your-pockettts-api-key
WINSTON_TTS_VOICE=jarvis-intro1
```

For a 24/7 VPS, those services must run on the VPS or point to a private reachable endpoint. If the VPS does not have Ollama/PocketTTS yet, keep `WINSTON_LLM_PROVIDER=rule_based` and `WINSTON_TTS_PROVIDER=browser` until those services are installed.

The deploy compose file includes an optional Ollama service. On the VPS, start it with:

```bash
docker compose --profile ai up -d ollama
docker compose exec ollama ollama pull qwen3:1.7b
docker compose exec ollama ollama pull qwen3.5:2b
```

Then set:

```text
WINSTON_LLM_PROVIDER=ollama
WINSTON_LLM_BASE_URL=http://ollama:11434
WINSTON_LLM_MODEL=qwen3:1.7b
WINSTON_LLM_TIMEOUT_SECONDS=20
WINSTON_LLM_MAX_TOKENS=120
WINSTON_LLM_THINK=false
WINSTON_RESEARCH_LLM_MODEL=qwen3.5:2b
WINSTON_RESEARCH_THINK=false
WINSTON_RESEARCH_MAX_TOKENS=320
WINSTON_RESEARCH_CONTEXT_CHARS=7000
WINSTON_RESEARCH_TIMEOUT_SECONDS=120
```

`WINSTON_LLM_THINK=false` is important for phone mode because Qwen thinking models can otherwise spend the response budget on hidden reasoning and return no spoken answer.

For VPS-hosted Winston voice, copy the Hermes PocketTTS bridge into `pockettts-agent-bridge`, start the optional compose profile, and point Winston to the private service:

```bash
docker compose --profile voice up -d pockettts
```

```text
WINSTON_TTS_PROVIDER=pockettts
WINSTON_TTS_BASE_URL=http://pockettts:8000/v1
WINSTON_TTS_VOICE=jarvis-intro1
```

The packaged stack includes a sanitized `pockettts-agent-bridge` folder with the bridge source and voice assets. It intentionally excludes `.env`, generated audio, local model cache, and virtualenv files. On first use, PocketTTS may recreate its model cache inside `data/hf-cache`.

## Apple Music

The private `.p8` key stays outside the browser. The bot generates a short-lived Apple Music developer token from these environment variables:

```text
APPLE_MUSIC_TEAM_ID=your-10-character-team-id
APPLE_MUSIC_KEY_ID=your-media-services-key-id
APPLE_MUSIC_PRIVATE_KEY_PATH=/absolute/path/to/AuthKey_KEYID.p8
APPLE_MUSIC_TOKEN_TTL_HOURS=12
APPLE_MUSIC_TOKEN_ORIGINS=https://your-bot-domain.example
```

Open the iPod panel and click `Connect Music`. The browser asks you to authorize Apple Music. After authorization, search from the iPod panel and press play on a result to queue it inside the dashboard. The MusicKit user authorization remains browser-side; the dashboard never displays or stores the private key.

The search box uses the bot's server-side Apple Music catalog endpoint:

```text
/api/apple-music/search?term=focus&storefront=us&limit=6
```

## Notes

TradingView is loaded from TradingView's public widget script. If that script cannot load, the monitor falls back to the local animated scanner canvas. ES remains in the bot watchlist, but the public widget can restrict some continuous futures symbols, so V5 uses QQQ as an embed-friendly chart companion to SPY.
