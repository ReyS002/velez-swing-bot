# Trading Bull Desk Dashboard V6.21

## V6.21 Hybrid Scanner

The command center now includes a `Hybrid VPS scanner` card. It shows whether the VPS scanner is running, its timeframe, the last scan time, how many lanes were scanned, and recent scanner decisions. The scanner complements TradingView alerts; it does not replace them.

Startup behavior is defensive: the scanner first warms indicator history from recent candles and does not submit trades from old bars. After warm-up, it only acts on newly closed bars.

Dashboard V6.21 keeps the Candidate C room as the main visual stage, keeps the front end named Trading Bull Desk, and hides the side controls so more of the room is visible. The monitor attempts to load TradingView's official Advanced Chart widget, while the local canvas chart remains underneath as a fallback if the external widget is blocked or slow. The iPod works as an in-desk Apple Music mini player through MusicKit JS, the desk phone supports Winston daily briefs, fast iPod commands, room-object commands, Research Mode, Deep Research, Hermes PocketTTS voice, guarded paper-order approvals, active-trade lifecycle readbacks, and Velez lot sizing, and the calendar pulls live broker, earnings, macro, and journal data.

## V6.21 Lot Conviction Pass

- Added Oliver Velez 1-to-4 lot sizing before actual share/contract quantity calculation
- 1 lot equals 25% of the configured max risk budget; 4 lots equals full configured risk
- A+ event candles such as Elephant Bars, 180s, Tail Bars, Opening Gap Go, and Time + Space Breakouts can start at 2 lots
- Power locations at the 20 SMA or 200 SMA can increase conviction to 3 lots
- Rare clean power setups with strong body/tail/recovery/time-space metrics can reach 4 lots
- Missing location, chased entries, wide stops, and extended continuation setups are capped defensively
- The Risk Command Center now shows Lot Flow, and journal confidence receipts include the selected lot plan

## V6.19 Trade Lifecycle Pass

- Added a read-only Alpaca lifecycle reconciler for live paper positions, open broker orders, and recent fills
- Added the laptop Trade Lifecycle Command Center with active trades, open risk, average R, stop source, and management-rule readbacks
- Added guardrail cards for missing stops, journal-only stops, orphan positions, max-position overages, broker snapshot errors, and pending-order overlap
- Added lifecycle outcome logging for active position, 1R reached, 2R reached, and guardrail milestone events
- Added Winston readbacks for active positions, stops, R multiples, breakeven, partial, and management questions
- Added `/api/lifecycle/state`, `/api/lifecycle/reconcile`, and `/api/lifecycle/outcomes`
- Bumped dashboard assets to `v=6.19`

## V6.18 Desk Intelligence Pass

- Added Winston Deep Research from the desk phone for higher-context prep memos
- Added confidence receipts to saved trade decisions and selected trade reviews
- Added Daily Close Report cards for laptop, journal, and Bull Report panels
- Expanded Alert Coverage with coverage score, payload checks, freshness, and setup counts
- Added Risk Replay sizing so replay scenarios can show what-if quantity/risk plans without broker orders
- Added VPS uptime/latency probes beside the existing hardening panel
- Bumped dashboard assets to `v=6.18`

## V6.17 Winston Hybrid Brain

- Upgraded Winston phone mode to support OpenAI-compatible DeepSeek APIs with explicit thinking controls
- Recommended `deepseek-v4-flash` for the live phone lane and `deepseek-v4-pro` for Research Mode
- Added local Ollama fallback configuration so Winston can still answer from the VPS if the cloud brain is unavailable
- Updated the phone panel label to show the DeepSeek hybrid brain and fallback model

## V6.16 Reliability Pass

- Added an Alert Coverage lane in Command Center for TradingView Watchlist Alert coverage and last alert received per symbol
- Added a guarded webhook dry-run button that records a `diagnostic` journal decision and never stages or submits an order
- Added clickable journal trade review with rule checks, next-symbol activity, chart link, and replay-this-setup actions
- Added a Risk Command Center with paper execution state, risk caps, paper-only guardrail, and approval-mode toggle protected by the local approval token
- Added Winston Morning Call from the desk phone
- Added VPS hardening helpers for health checks, backups, restart policy install, and dashboard hardening status

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

## V6.15 Opening Gap / Time + Space Brain

- Added `opening_gap_go`, `opening_gap_fade`, and `time_space_breakout` to the Velez strategy engine
- Added gap direction, gap percent, prior close, first opening range, clean-space score, obstacle, and gap-fill metadata
- Updated the TradingView Pine alert script with opening-gap/time-space inputs and alert payload fields
- Added new replay scenarios to the Backtest Drawer and Command Center
- Bumped dashboard assets to `v=6.15`

## V6.14 Logo Refresh

- Replaced the dashboard header logo with the new gold-and-blue bull mark
- Added a `v=6.14` cache-buster to the logo image, CSS, and JS assets
- Rounded the header logo frame so the mark appears as a compact circular badge

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

## V6.13 Watchlist Form Stability

- Fixed the Command Center watchlist form so the 5-second live refresh no longer clears the symbol field while typing
- Preserved the in-progress symbol and asset type until the add action succeeds
- Deferred automatic panel re-renders while a dashboard form field is focused
- Bumped dashboard assets to `v=6.13`

## V6.12 Strategy Expansion

- Added Velez Buy Setup and Sell Setup modules for controlled pullbacks into the 20/200 SMA structure
- Added NRB/Acorn continuation entries from narrow-range pause bars
- Added first color-change add signals with mandatory 50% add-to-winner sizing and existing-position guardrails
- Added Fab 4 trap-zone breakout detection when the 20 SMA, 200 SMA, price, and range compress
- Added Failed New High and Failed New Low reversal traps
- Added Velez-style management metadata for bar-3 profit review, 1R/2R targets, breakeven movement, bar-by-bar trailing, and exhaustion checks
- Updated the TradingView Pine alert script to emit the expanded play list
- Bumped dashboard assets to `v=6.12`

## V6.11 Object Hitbox Polish

- Shrunk the Call Winston hotspot around the visible desk phone body
- Tightened the Strategy Library hotspot to the left shelf so it feels less oversized
- Moved the Risk Mood Light hotspot onto the top of the desk lamp
- Bumped dashboard assets to `v=6.11` for a clean browser refresh

## V6.10 Shelf Bull Hotspot

- Moved Bull Report from the desk bull to the gold bull on the right shelf
- Shrunk and lowered the Credential Safe hotspot so it no longer competes with the shelf bull
- Bumped dashboard assets to `v=6.10` for a clean browser refresh

## V6.9 Desk Object Polish

- Moved the Backtest drawer hotspot onto the right physical desk drawer
- Renamed the sticky-note surface to Bull Report
- Moved the Bull Report hotspot onto the small gold bull on the desk
- Winston can open it with phrases like `open bull report`, `open after action review`, or `open notes`
- Bumped dashboard assets to `v=6.9` for a clean browser refresh

## V6.8 Phone Plate Revert

- Reverted the active day/night room plates to the original smaller Winston phone because it fits the desk perspective better
- Kept the original smoke/diffuser atmosphere rather than the cleaned patch, which introduced visible pixelation
- Restored the smaller Winston phone hotspot footprint
- Bumped dashboard assets to `v=6.8` so browsers refresh away from the V6.7 Cisco-style phone plate

## V6.7 Desk Phone Plate Update

- Replaced the remaining diffuser/smoke phone area in both day and night room plates with a larger Cisco-style desk phone based on the provided reference image
- Shifted the phone left and remapped the Winston hotspot to the new visible phone footprint
- Preserved the iPod/music device as a separate desk object
- Bumped dashboard assets to `v=6.7` so browsers refresh the new plates

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
