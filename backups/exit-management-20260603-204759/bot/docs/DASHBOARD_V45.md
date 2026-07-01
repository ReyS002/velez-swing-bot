# Velez Bot Dashboard V4.5

Dashboard V4.5 keeps the photoreal office plate as the visual source of truth and removes the visible Three.js desk props. The room objects in the image now act as interactive hotspots, while the trading chart remains a lightweight 2D canvas screen.

## URL

Local:

```text
http://127.0.0.1:8080/dashboard
```

VPS:

```text
https://velezbot.72.62.169.3.nip.io/dashboard
```

## V4.5 Upgrades

- Removed the visible Three.js journal, safe, calendar, music device, laptop, candle, and Jarvis meshes
- Added image-aligned invisible hotspots over the photoreal room plate
- Kept the real journal on the desk as the clickable journal target
- Converted the trading screen into a flatter CSS/canvas overlay instead of a 3D monitor mesh
- Added subtle hover/focus outlines only when the user interacts with an object
- Preserved the read-only dashboard panels, live bot status, paper broker state, positions, and recent alert journal

## How Interaction Works

The room background is treated like a scaled image. JavaScript calculates the visible image rectangle created by `background-size: cover`, then positions each hotspot using normalized image coordinates. This keeps the clickable regions attached to the journal, desk, shelves, drawers, candle area, and Jarvis zone across desktop sizes.

## Remaining Limits

- The trading chart is still a canvas-rendered scanner view, not an embedded TradingView widget.
- The monitor is still an overlay because the V4 room plate does not contain a physical monitor.
- Mobile uses the bottom icon rail instead of image hotspots to avoid cramped object targeting.
- Jarvis voice and live Q/A remain staged for V5.
