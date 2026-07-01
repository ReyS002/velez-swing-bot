# Trading Bull Desk TODO

## Completed In V6.21

- Added Oliver Velez 1-to-4 lot conviction sizing before quantity calculation
- Mapped A+ event candles, 20 SMA power positions, 200 SMA battle zones, power body/tail/recovery metrics, and opening time-space quality into lot decisions
- Kept lots inside the existing max risk budget: 1 lot is 25% of max risk and 4 lots is full configured risk
- Added defensive caps for missing location, chased entries, wide stops, and extended continuation setups
- Added lot-plan metadata to journal confidence receipts and risk readbacks
- Updated TradingView Pine alerts to send candle quality metrics used by the lot engine
- Updated risk replay to show the 1-4 lot risk ladder
- Packaged the full Oliver Velez strategy brain as a reusable skill download
- Bumped dashboard assets to `v=6.21`

## Completed In V6.19

- Added read-only Alpaca lifecycle reconciliation for live paper positions, open orders, and recent fills
- Added the Trade Lifecycle Command Center to the laptop with R multiple, stop source, open risk, and management-rule readbacks
- Added Winston active-trade lifecycle readbacks for questions about positions, stops, R multiple, partials, and breakeven status
- Added persistent lifecycle snapshots and trade outcome events for open position, 1R, 2R, and guardrail milestones
- Added lifecycle guardrail alerts for missing stops, journal-only stops, orphan positions, max-position overages, broker snapshot errors, and pending-order overlap
- Added `/api/lifecycle/state`, `/api/lifecycle/reconcile`, and `/api/lifecycle/outcomes`
- Bumped dashboard assets to `v=6.19`

## Completed In V6.18

- Added Winston Deep Research as a higher-context research lane from the desk phone
- Added confidence receipts to journal entries and selected trade reviews
- Added Daily Close Report cards across the laptop, journal, and Bull Report panels
- Expanded alert coverage with payload/freshness checklist rows and a coverage score
- Added risk replay sizing variants for replay scenarios without broker submission
- Added VPS uptime/latency probes and bumped dashboard assets to `v=6.18`

## Completed In V6.15

- Added the Velez opening-gap and time-space strategy layer to the trading brain
- Added `opening_gap_go`, `opening_gap_fade`, and `time_space_breakout` plays
- Added gap direction, prior close, first opening range, clean-space score, obstacle, and gap-fill metadata
- Updated the TradingView Pine alert script to emit the new opening-gap/time-space play names
- Added replay samples for the new opening setups and exposed them in the Backtest Drawer
- Bumped dashboard assets to `v=6.15`

## Completed In V6.14

- Replaced the dashboard brand mark with the new gold-and-blue bull logo
- Added logo cache busting with `trading-bull-logo.png?v=6.14`
- Rounded the header logo frame so the new mark reads as a clean circular badge
- Bumped dashboard assets to `v=6.14`

## Completed In V6.13

- Fixed the watchlist add form so live dashboard refreshes no longer reset the symbol field while typing
- Preserved the in-progress symbol/type draft during panel updates
- Deferred non-critical panel re-renders while a dashboard form input is focused
- Bumped dashboard assets to `v=6.13` so browsers refresh the stabilized watchlist controls

## Completed In V6.12

- Added Velez Buy Setup and Sell Setup detection after controlled pullbacks into key moving-average locations
- Added NRB/Acorn continuation breaks from narrow-range pause bars
- Added first color-change add signals with mandatory 50% add-to-winner sizing guardrails
- Added Fab 4 trap-zone breakout detection from compressed 20/200 SMA structure
- Added Failed New High and Failed New Low reversal traps
- Added Velez-style management metadata: bar-3 profit check, 1R/2R targets, breakeven move, bar-by-bar trail, and exhaustion watch
- Updated the TradingView Pine alert script to emit the new play names and color-change add metadata
- Bumped dashboard assets to `v=6.12` so the live bot reports the expanded strategy package

## Completed In V6.11

- Shrunk the Call Winston hotspot around the desk phone body
- Tightened the Strategy Library hotspot to the left shelf
- Moved the Risk Mood Light hotspot onto the top of the desk lamp
- Bumped dashboard assets to `v=6.11` so browsers refresh the updated object map

## Completed In V6.10

- Moved the Bull Report hotspot from the desk bull to the gold bull on the right shelf
- Tightened the Credential Safe hotspot so it stays focused on the safe door
- Bumped dashboard assets to `v=6.10` so browsers refresh the updated object map

## Completed In V6.9

- Moved the Backtest drawer hotspot onto the right physical desk drawer
- Renamed the sticky-note panel to Bull Report
- Moved the Bull Report hotspot onto the small gold bull on the desk
- Bumped dashboard assets to `v=6.9` so browsers refresh the object map

## Completed In V6.8

- Reverted the active room plates back to the original smaller integrated Winston phone
- Kept the original smoke/diffuser look because it blends better with the room than the cleaned/pixelated patch
- Restored the smaller Winston phone hotspot footprint
- Bumped dashboard assets to `v=6.8` so browsers leave the V6.7 Cisco-style overlay behind

## Completed In V6.7

- Replaced the baked-in Winston phone/diffuser area with a larger Cisco-style desk phone in both day and night room plates
- Removed the visible smoke/diffuser residue behind the phone area
- Moved and enlarged the Winston phone hotspot so it matches the new left-shifted desk phone
- Bumped dashboard assets to `v=6.7` to force browsers to load the updated room plates

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
## Completed In V6.21

- Added hybrid VPS watchlist scanner inside the webhook service.
- Scanner pulls Alpaca market-data candles, warms up indicator history, ignores stale startup candles, and only routes newly closed bars.
- Scanner decisions use the same Oliver Velez brain, 1-to-4 lot sizing, risk checks, max-position guardrails, paper endpoint lock, and journal receipts as TradingView alerts.
- Dashboard now shows hybrid scanner status in the command center.
