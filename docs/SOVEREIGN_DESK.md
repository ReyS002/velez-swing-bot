# Sovereign Desk

Production code is under bot/. The edition keeps its own trading engine, account permissions and handlers. The room shell, artwork, and Broadcast code must remain identical in Bull Pilot, Velez Bot, and Velez Swing.

Five calibrated rooms each have two lighting plates. Geometry is defined in bot/static/dashboard/sovereign-room.js as percentages of a 1672×941 plate and uses a shared contain-fit viewport calculation. Desktop charts use the existing TradingView widget; expansion is available on desktop and mobile. Chart bookmarks do not claim to be captured chart pixels.

## Room controls

- Glass handset → Winston. Opening it never starts a call. Start Call is explicit inside the panel.
- Smaller pocket player → existing Apple Music connection and playback controls.
- Journal → trades; related tab → Bull Report and notes.
- Session Brief → mission, calendar, sessions, conditions; Watchlist opens Command.
- Keyboard and trackpad → Command.
- Lamp → Bull Matrix and risk controls. Lighting is in the header.
- Approval drawer → approvals, vault and service status.
- Bookshelf → strategy library. Bull statue → Bull Report and notes.
- Tools → all original panels, including Research lab, Account, and Velez Pro Console.
- Broadcast → one player retained between rooms; left wall in scenic rooms, upper wide wall screen in Executive. Hidden-tab playback pauses. Winston speech lowers both player volumes and restores the user's selected volume afterward.

## Read-only presentation configuration

GET /api/desk/config exposes product, broker provider, account mode and access tier, with no credentials. GET /api/broadcast/config describes explicit media assignment. These routes use the existing dashboard authentication middleware.

DESK_BROADCAST_ENABLED controls availability, with the existing BULLPILOT_BROADCAST_ENABLED honored as fallback. DESK_BROADCAST_YOUTUBE_VIDEO_ID, DESK_BROADCAST_YOUTUBE_CHANNEL_URL, or DESK_BROADCAST_VIDEO_URL assign media. Unassigned workspaces display the bundled preview with a PREVIEW label; no live-channel claim is made. Market feeds use the existing DENDRIX_BROADCAST_FEED_URL/TOKEN or available Alpaca data connection, with explicit unavailable values for uncovered instruments.

Apple Music subscriber authorization and broker OAuth remain private user sessions. The room redesign does not replace those credentials, activate trading, authorize orders, or invent unavailable market data. Winston is the existing assistant, not a public telephone service.

## Verification

Bull Pilot: npm run test:e2e and the Python suite. Velez: npm run test:visual and the Python suite. Visual baselines are generated in the pinned Playwright Linux container used by CI. Shared-shell edits should be verified against all five rooms, both lighting modes, mobile navigation, original feature panels, and Broadcast playback continuity.

## Room refinements (1.0.1)

The phone stays grounded without an offset shadow or lift on hover. The pocket player sits farther back beside each room’s keyboard. Broadcast uses calibrated clockwise wall corners, projected with a CSS matrix across the full player and its controls. Opening and returning use a reversible 440 ms transform on the existing player; the video element and playback session are never replaced. The expanded view stays wide and centered. Reduced motion skips the transition; resizing or changing rooms cancels an in-flight movement and uses the current destination. No room artwork or trading configuration changes in this refinement.


## Adaptive glass (1.1.0)

All five rooms use clear champagne glass with dark text in day/Focus lighting and smoked glass with ivory text in night/Cinema/Sunset/Blue Hour lighting. The shared surface layer covers every detail panel, related tabs, Tools, Pro Console where available, and expanded Broadcast controls. Charts and video remain opaque. Existing forms, data, actions, and object positions are preserved. The fixed side panel uses one content column so older wide-workflow styles cannot split it into cramped columns.

Panel background opacity is separate from content opacity; lightly frosted panels reveal the room while denser translucent cards protect text. Reduced-transparency preferences request stronger surfaces. Browsers without backdrop-filter use a stronger fallback. Keyboard outlines follow the active glass palette.

The phone keeps its existing raster artwork and size. Its native SVG silhouette now follows the curved base more closely, excluding the baked pale background at the sides and underneath; its existing grounded hover behavior remains.
