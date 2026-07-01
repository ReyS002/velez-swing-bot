# Velez Bot Dashboard V1

Dashboard V1 is a read-only visual command room served by the same FastAPI webhook service that receives TradingView alerts.

## URL

Local:

```text
http://127.0.0.1:8080/dashboard
```

VPS:

```text
https://velezbot.72.62.169.3.nip.io/dashboard
```

## What It Shows

- 3D desk view with a live-style trading screen
- Bot execution state: proposal mode or paper execution armed
- Alpaca paper broker connection status
- Open-position count and unrealized P/L from Alpaca
- Risk settings from `bot/config.yaml`
- Recent TradingView decisions from this bot process
- Clickable room objects for TV, command center, journal, calendar, safe, music, and Jarvis

## Security

The dashboard does not expose Alpaca API keys, Alpaca secret keys, or the TradingView webhook secret. Broker health only returns safe account metadata such as paper status and the last four characters of the account number.

## How It Works

The server exposes:

```text
/dashboard
/api/dashboard/state
```

Static files live in:

```text
bot/static/dashboard/
```

The dashboard polls `/api/dashboard/state` and renders the 3D office with Three.js in the browser.

## V1 Limits

- TradingView charting is represented by an animated dashboard canvas, not an embedded TradingView widget.
- Jarvis voice and company Q/A are staged as an interface lane, not connected yet.
- The calendar panel is prepared for an events feed, but does not yet pull FOMC, CPI, or earnings data.
- The music panel opens Apple Music, but no personal playlist is linked yet.
