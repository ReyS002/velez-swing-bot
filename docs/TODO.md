# Trading Bull Desk TODO

## Completed In V6.6

- Added Daily Mission as a first-class room object with session, event, risk, approvals, review, and watchlist heat context
- Added browser-side trade screenshot capture from the desk chart canvas and linked TradingView chart context in journal cards
- Added Winston after-action review via `/api/review/daily` and review cards in Mission, Journal, and Notes
- Added market event countdown cards to Mission, Calendar, and Clock
- Added Approval Inbox to the safe, wired to the existing guarded paper-order approval route
- Added subtle object glow states for pending approvals, event risk, live phone/music, saved captures, and locked EOD status
- Added watchlist heat strips to Trading Screen, Mission, Laptop, and Window
- Added End-of-Day Lock Ritual in Notes/Mission using browser-local review snapshots

## Completed In V6.5

- Added interactive object panels for bookshelf, desk clock, window view, risk lamp, backtest drawer, and sticky notes
- Expanded the laptop with command shortcuts into the new room objects
- Expanded the safe with Apple Music, Winston, approval-token, and webhook status checks
- Added Winston fast-router support for opening the new room objects by voice/text

## Completed In V6.4

- Forced a fresh dashboard asset version after the Winston/iPod wiring
- Hardened Winston iPod commands so they search/show results immediately and never stall on browser Apple Music authorization
- Winston now asks for one manual `Connect Music` click before voice-triggered playback when the browser is not authorized

## Completed In V6.2

- Winston fast command router for deterministic iPod and panel commands
- Browser-side Apple Music actions from Winston phone responses
- VPS model smoke test; selected `qwen3:1.7b` for phone mode
- Kept `qwen3.5:2b` reserved for Winston Research Mode

## Completed In V6.1

- Live bot health panel
- Polished persistent journal cards with setup grade and risk readback
- Calendar timeline combining sessions, macro, earnings, and journal activity
- Replay mode for safe Velez rule checks
- Winston daily brief upgraded with health, readiness, and watch-plan context

## Completed In V6.0

- Daily Brief Mode
- Persistent SQLite journal
- Watchlist management UI
- Winston Research Mode
- Guarded paper-order approval flow

## Next Ideas

- Add authenticated dashboard login before exposing approval controls on a custom public domain.
- Add per-symbol earnings/fundamentals panels for the laptop and calendar.
