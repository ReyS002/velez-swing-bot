# Velez Bot Dashboard V4

Dashboard V4 switches the room to a hybrid photoreal approach: a generated architectural background plate provides the realistic luxury office shell, and Three.js renders the live trading monitor, laptop, clickable props, screen glow, and Jarvis layer in front.

## URL

Local:

```text
http://127.0.0.1:8080/dashboard
```

VPS:

```text
https://velezbot.72.62.169.3.nip.io/dashboard
```

## V4 Upgrades

- Photoreal executive office background plate with city skyline, warm shelving, glass wall, and walnut desk
- Transparent Three.js foreground layer instead of a fully procedural room
- Live animated trading monitor placed over the desk
- Smaller interactive laptop, journal, safe, calendar, music, candle, and Jarvis elements layered into the scene
- Better visual hierarchy: the office shell looks photographic while the bot UI remains interactive
- Reduced WebGL scene complexity because the photoreal shell is a static image asset

## Asset

The background plate lives at:

```text
bot/static/dashboard/v4-office-plate.png
```

The source generated image is preserved under the Codex generated-images directory.

## Security

The dashboard remains read-only. It does not expose Alpaca API keys, Alpaca secret keys, or the TradingView webhook secret. Broker health only returns safe account metadata such as paper status and the last four characters of the account number.

## V4 Limits

- The office shell is a generated bitmap plate, not a fully navigable 3D room.
- The trading screen is a canvas-rendered chart, not an embedded TradingView widget yet.
- Jarvis voice and live Q/A are still staged visually.
- Calendar events and Apple Music personalization are not connected yet.
