# Velez Bot Dashboard V2

Dashboard V2 is the first polished pass on the signature trading-room interface. It is still served by the same FastAPI webhook service, and it remains read-only.

## URL

Local:

```text
http://127.0.0.1:8080/dashboard
```

VPS:

```text
https://velezbot.72.62.169.3.nip.io/dashboard
```

## V2 Upgrades

- Procedural wood, wall, floor, rug, and window textures
- Larger trading monitor with animated candles, SMA lines, price marker, and volume bars
- More realistic laptop workstation with visible keyboard, command screen, mouse, desk lamp, plant, shelf, and city window
- Rounded monitor, laptop, safe, journal, and desk geometry for less blocky shapes
- Subtle camera parallax and animated room details
- More dimensional Jarvis bay with hologram rings and particle field
- Mobile layout check for fitted object dock and non-overlapping panels

## What It Still Protects

The dashboard does not expose Alpaca API keys, Alpaca secret keys, or the TradingView webhook secret. Broker health only returns safe account metadata such as paper status and the last four characters of the account number.

## V2 Limits

- TradingView charting is still represented by an animated dashboard canvas, not an embedded TradingView widget.
- Jarvis voice and company Q/A are staged visually, not connected to a live agent yet.
- Calendar events are staged for a feed, but FOMC, CPI, and earnings are not connected yet.
- Apple Music opens externally; no personal playlist is linked yet.
