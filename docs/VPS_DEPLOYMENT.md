# VPS Deployment Notes

The Velez Trading Bot webhook is deployed on the Hostinger VPS as a Docker/Traefik service.

## VPS

```text
Host: srv1668095.hstgr.cloud
IP: 72.62.169.3
Stack path: /opt/stacks/velez-trading-bot
Container: velez-trading-bot-webhook
Public host: velezbot.72.62.169.3.nip.io
```

## Public URL

Health:

```text
https://velezbot.72.62.169.3.nip.io/health
```

Visual dashboard:

```text
https://velezbot.72.62.169.3.nip.io/dashboard
```

Dashboard state API:

```text
https://velezbot.72.62.169.3.nip.io/api/dashboard/state
```

Calendar API:

```text
https://velezbot.72.62.169.3.nip.io/api/calendar/month
```

Winston AI status:

```text
https://velezbot.72.62.169.3.nip.io/api/winston/status
```

Apple Music developer-token API:

```text
https://velezbot.72.62.169.3.nip.io/api/apple-music/developer-token
```

TradingView webhook:

```text
https://velezbot.72.62.169.3.nip.io/webhook/tradingview/YOUR_WEBHOOK_SECRET
```

The real secret is stored on the VPS in:

```text
/opt/stacks/velez-trading-bot/.env
```

Apple Music's private `.p8` key is stored outside the app code and mounted read-only into the container from:

```text
/opt/stacks/velez-trading-bot/secrets/
```

Winston's local voice bridge is stored beside the app code and is only reachable on the private Docker network:

```text
/opt/stacks/velez-trading-bot/pockettts-agent-bridge/
```

## Current Mode

The service is currently armed for Alpaca paper execution:

```text
VELEZ_EXECUTE_ORDERS=true
```

That means qualified TradingView alerts can submit Alpaca paper orders. The bot still rejects non-paper Alpaca endpoints by default.

## Enable Alpaca Paper Execution

Edit the VPS env file:

```bash
cd /opt/stacks/velez-trading-bot
nano .env
```

Set:

```text
APCA_API_KEY_ID=your-paper-key
APCA_API_SECRET_KEY=your-paper-secret
APCA_API_BASE_URL=https://paper-api.alpaca.markets
VELEZ_EXECUTE_ORDERS=true
VELEZ_APPROVAL_API_TOKEN=your-separate-approval-token
VELEZ_DATA_DIR=/app/data
```

Restart:

```bash
docker compose up -d
```

The bot still rejects non-paper Alpaca endpoints by default.

## Calendar Feeds

The calendar panel uses Alpaca for month P/L, open-position mark, and market sessions. It uses Alpha Vantage for watchlist earnings and free official sources for macro events.

Set this in `/opt/stacks/velez-trading-bot/.env`:

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

Restart after changes:

```bash
cd /opt/stacks/velez-trading-bot
docker compose --profile ai --profile voice up -d --build webhook
```

## Persistent Journal And Approval Flow

The webhook container mounts VPS storage at `/app/data`:

```text
./data:/app/data
```

The SQLite desk database lives under `VELEZ_DATA_DIR` and stores recent decisions, watchlist edits, research notes, and pending approval orders. Keep this in `.env`:

```text
VELEZ_DATA_DIR=/app/data
VELEZ_AUTO_STAGE_PROPOSED_ORDERS=true
VELEZ_REQUIRE_ORDER_APPROVAL=false
VELEZ_APPROVAL_TTL_MINUTES=30
VELEZ_APPROVAL_API_TOKEN=your-separate-approval-token
```

The guarded approval endpoint requires the browser-supplied approval token plus the exact phrase shown by Winston. It only submits through Alpaca paper when execution is armed and the staged order was produced by the bot's own risk-checked proposal path.

Useful endpoints:

```text
/api/brief/daily
/api/watchlist
/api/orders/pending
/api/winston/research
```

## Apple Music iPod

Set these in `/opt/stacks/velez-trading-bot/.env`:

```text
APPLE_MUSIC_TEAM_ID=your-10-character-team-id
APPLE_MUSIC_KEY_ID=your-media-services-key-id
APPLE_MUSIC_PRIVATE_KEY_PATH=/opt/stacks/velez-trading-bot/secrets/AuthKey_KEYID.p8
APPLE_MUSIC_TOKEN_TTL_HOURS=12
APPLE_MUSIC_TOKEN_ORIGINS=https://your-bot-domain.example
```

The compose file mounts `./secrets` read-only so the bot can sign short-lived MusicKit developer tokens without copying the `.p8` key into the image. Once a browser authorizes Apple Music, the iPod panel can search, queue, and control browser playback inside Trading Bull Desk.

## Winston AI And Voice

The VPS runs Winston with an Ollama brain and a private PocketTTS voice service. The current live profile is:

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
WINSTON_TTS_PROVIDER=pockettts
WINSTON_TTS_BASE_URL=http://pockettts:8000/v1
WINSTON_TTS_VOICE=jarvis-intro1
```

The PocketTTS service uses a separate private env file:

```text
/opt/stacks/velez-trading-bot/.env.pockettts
```

To restart the full AI and voice stack:

```bash
cd /opt/stacks/velez-trading-bot
docker compose --profile ai --profile voice up -d webhook ollama pockettts
```

Voice requests are routed through the bot at `/api/winston/speech`; the browser never talks directly to the PocketTTS container. Voice chat remains read-only for trade execution: Winston can brief, explain, and read back pending context, but it cannot submit orders by voice.

## Operations Commands

Check status:

```bash
cd /opt/stacks/velez-trading-bot
docker compose ps
```

View logs:

```bash
docker logs -f velez-trading-bot-webhook
```

Restart:

```bash
cd /opt/stacks/velez-trading-bot
docker compose restart
```

Rebuild after code changes:

```bash
cd /opt/stacks/velez-trading-bot
docker compose --profile ai --profile voice up -d --build
```

## Optional Real Domain

The bot is currently using a free `nip.io` hostname that resolves to the VPS IP. To use your own domain, add an A record such as:

```text
bot.bulldesk.tech -> 72.62.169.3
```

Then change:

```text
VELEZ_PUBLIC_HOST=bot.bulldesk.tech
```

in `/opt/stacks/velez-trading-bot/.env`, and run:

```bash
docker compose up -d
```
