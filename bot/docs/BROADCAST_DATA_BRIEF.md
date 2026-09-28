# Broadcast and desk information release — 1.2.0

The wall Broadcast now opens a channel selector in every room. One player retains the selected channel and audio settings across room changes. Bloomberg, Yahoo Finance and Schwab use verified official YouTube streams. tastylive and Federal Reserve have explicitly labeled replays. Academy remains Coming soon until its owner creates a channel. Playback requires a user gesture; blocked or ended streams provide an official-channel link. YouTube Premium is a personal viewing account, not a server integration credential.

Winston Desk Brief prepares a private, timestamped snapshot using the existing Daily Brief, independent display quotes and shared earnings calendar. Read displays the facts. Listen and Watch brief narrate those same cards through the existing locked Winston voice; cards advance when their audio ends. Ask Winston retains the snapshot for 30 minutes, uses Winston’s primary brain independently of legacy research-provider settings, and cannot invoke the execution-command dispatcher. Brief text/audio are kept in browser memory, never local storage. Only public channel/audio preferences persist.

## Runtime settings

- `DESK_DISPLAY_TRADIER_TOKEN`, `DESK_DISPLAY_TRADIER_ENV=production`: independent consolidated equity, ETF and VIX display reads. Sandbox is labeled delayed.
- `DESK_DISPLAY_ALPACA_KEY`, `DESK_DISPLAY_ALPACA_SECRET`, `DESK_DISPLAY_ALPACA_FEED=iex`: independent crypto feed and stock fallback. IEX/SIP/delayed SIP are explicitly distinguished.
- `DESK_EARNINGS_CACHE_PATH=/app/shared-market/earnings.json`: same writable host directory mounted into all three editions. `ALPHA_VANTAGE_API_KEY` refreshes the full three-month CSV every 12 hours; cross-process locking and 30-minute failure backoff avoid duplicate downloads. Failed refreshes preserve the last valid rows. Earnings timing is not invented.
- `BLS_SHARED_CACHE_FILE=/app/data/shared-calendar/bls-calendar.json`: one host-backed calendar cache shared by all three editions. A file lock limits BLS to one refresh sequence every 12 hours. The downloader uses spaced retries, conditional requests, a short failure backoff, the last valid cache during outages, and the official monthly BLS list as its fallback. `BLS_HTTP_USER_AGENT` can override the default downloader identity, which includes owner contact information for BLS automated-access policy.
- `DESK_BROADCAST_CHANNELS_PATH=/app/broadcast-channels.json`: optional administrator-owned JSON file for managed assignments. Existing channel keys accept validated `label`, `category`, `youtube_video_id`, `youtube_playlist_id`, `youtube_channel_url`, and `kind`. A validated `channels` array can add administrator defaults, up to 14 total. A channel URL alone provides the Visit Channel fallback; a video or playlist ID provides in-desk playback. The Tools → Channel Manager stores each user's enabled, ordered, and personal lineup in that browser. Reload the page after server assignment changes.

Example future Academy assignment (replace placeholders with real verified identifiers):

```json
{"academy":{"kind":"replay","youtube_playlist_id":"PL_VALID_PLAYLIST_ID","youtube_channel_url":"https://www.youtube.com/@YOUR_CHANNEL"}}
```

`GLD` is labeled as an ETF. DXY, EUR/USD and spot gold were not returned by the existing Tradier catalog probes; no substitute prices or new paid provider are introduced. Each quote exposes source, timestamp, freshness, delay, fallback and market-session state. Bull Pilot display reads work independently of Robinhood readiness.

## Verification and deployment

Run the existing Python and browser suites plus `test_desk_broadcast_release.py`. Live checks must cover all editions, room geometry, channel switching, actual stream playback, blocked streams, mobile, private brief authentication, real narration, follow-ups, shared earnings timestamps, and disarmed execution state.

Deploy immutable images with the complete existing Compose override chain. Add only the approved display settings, shared cache and managed channel-file mount. Preserve broker configuration, persistent data, Apple Music signing, Fish Audio settings and HTTPS. Roll back by using the preceding override chain and images.
