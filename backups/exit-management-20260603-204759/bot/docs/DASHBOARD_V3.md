# Velez Bot Dashboard V3

Dashboard V3 moves the command room toward a realistic executive trading office inspired by floor-to-ceiling city-view workspaces.

## URL

Local:

```text
http://127.0.0.1:8080/dashboard
```

VPS:

```text
https://velezbot.72.62.169.3.nip.io/dashboard
```

## V3 Upgrades

- Full-width glass wall with dusk skyline, city lights, mullions, and subtle reflections
- Built-in warm bookshelves on both sides of the room
- Executive desk composition with drawer banks, glossy wood, large trading monitor, laptop, lamp, journal, plant, candle, and music device
- Desk-mounted trading screen instead of a wall-mounted prototype monitor
- Cleaner luxury-office visual language with fewer overt training labels
- Optimized WebGL cost after adding V3 detail by lowering max pixel ratio and replacing shelf point lights with emissive strips
- Existing live bot state, object panels, Jarvis toggle, recent decisions, and safety redaction preserved

## Security

The dashboard remains read-only. It does not expose Alpaca API keys, Alpaca secret keys, or the TradingView webhook secret. Broker health only returns safe account metadata such as paper status and the last four characters of the account number.

## V3 Limits

- The skyline is procedural canvas art, not a licensed photographic plate.
- TradingView charting is still represented by an animated dashboard canvas, not an embedded TradingView widget.
- Jarvis voice and company Q/A are staged visually, not connected to a live agent yet.
- Calendar events and Apple Music personalization are not connected yet.
