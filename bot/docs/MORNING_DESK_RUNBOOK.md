# Morning Desk Runbook

Use this before the bot is left running for a market session.

## 1. Confirm Access And Mode

```bash
export VELEZ_PUBLIC_URL="https://velezbot.72.62.169.3.nip.io"
curl -fsS "$VELEZ_PUBLIC_URL/health"
curl -fsS -u "$VELEZ_DASHBOARD_USERNAME:$VELEZ_DASHBOARD_PASSWORD" "$VELEZ_PUBLIC_URL/api/bot/health"
```

Confirm:

- Dashboard auth works.
- Alpaca endpoint is paper.
- Execution mode is the intended mode for the day.
- Approval mode is required when positions are over cap, stops are missing, or you want manual review.

## 2. Check Open Positions First

```bash
curl -fsS -u "$VELEZ_DASHBOARD_USERNAME:$VELEZ_DASHBOARD_PASSWORD" "$VELEZ_PUBLIC_URL/api/lifecycle/state"
```

Confirm:

- Open positions are at or below `risk.max_open_positions`.
- Every open position has broker stop protection or an intentionally documented journal stop.
- R multiple is computable for each active trade.
- No orphan positions, missing stops, pending-order overlaps, or max-position guardrails are active.

If lifecycle guardrails are active, do not rely on auto-submit. Keep `VELEZ_REQUIRE_ORDER_APPROVAL=true` until the guardrails are resolved.

## 3. Check Scanner And Alert Coverage

```bash
curl -fsS -u "$VELEZ_DASHBOARD_USERNAME:$VELEZ_DASHBOARD_PASSWORD" "$VELEZ_PUBLIC_URL/api/scanner/status"
curl -fsS -u "$VELEZ_DASHBOARD_USERNAME:$VELEZ_DASHBOARD_PASSWORD" "$VELEZ_PUBLIC_URL/api/scanner/quality"
curl -fsS -u "$VELEZ_DASHBOARD_USERNAME:$VELEZ_DASHBOARD_PASSWORD" "$VELEZ_PUBLIC_URL/api/watchlist/quality"
curl -fsS -u "$VELEZ_DASHBOARD_USERNAME:$VELEZ_DASHBOARD_PASSWORD" "$VELEZ_PUBLIC_URL/api/alerts/coverage"
```

Confirm:

- Scanner is running.
- Last scan time is fresh.
- `pause.paused` is false unless max exposure is intentionally reached.
- `today.counts` shows the scanner's submitted/proposed/diagnostic/rejected mix for the session.
- Scanner Quality shows accepted/rejected/skipped events, forward-replay outcomes, symbol stats, and session-bucket stats.
- Watchlist Quality Manager marks lanes as `promote`, `keep_watching`, `cool_down`, or `disable_candidate`. Applying promote/cooldown/disable actions requires the approval token.
- Skipped lanes are understood.
- TradingView coverage has no unexpected stale or never-seen symbols.
- Futures lanes are either configured with Polygon or intentionally disabled.

When `pause.paused=true` with `reason=max_exposure_reached`, the VPS scanner is intentionally calm: it stops looking for new entries until broker positions/open orders/staged exposure drop below the configured max-position cap. Per-symbol rejected signals also enter a cooldown window so the journal is not flooded with repeated same-symbol rejects.

Scanner operator controls are available from the dashboard and authenticated API:

- `POST /api/scanner/mode` with `mode=auto_submit`, `diagnostic`, or `paused` plus the approval token.
- `POST /api/scanner/orders/cancel-stale` with the approval token to cancel orphan scanner entry orders only.
- `POST /api/watchlist/quality/action` with `symbol`, `action`, and the approval token to mark a lane or disable/re-enable it.
- `POST /api/scanner/quality/notify` with the approval token to send the quality report to configured notification targets.
- Exposure details list positions, open orders, and staged approvals that count toward the scanner cap.
- The scanner session filter blocks noisy equity windows by default: before `09:35 ET`, lunch chop, and after `15:45 ET`. Crypto/futures lanes are not blocked by the equity RTH filter.
- Telegram/file notifications fire when exposure pause state changes between paused and resumed.

## 4. Check Calendar And Daily Brief

```bash
curl -fsS -u "$VELEZ_DASHBOARD_USERNAME:$VELEZ_DASHBOARD_PASSWORD" "$VELEZ_PUBLIC_URL/api/calendar/month"
curl -fsS -u "$VELEZ_DASHBOARD_USERNAME:$VELEZ_DASHBOARD_PASSWORD" "$VELEZ_PUBLIC_URL/api/brief/daily"
```

Confirm:

- Macro/session events are visible.
- Earnings/event risk is understood for watchlist names.
- Winston's brief matches the dashboard state.

## 5. Notification Readiness

At least one notification target should be configured for unattended operation:

```text
VELEZ_NOTIFY_ENABLED=true
VELEZ_NOTIFY_FILE=/app/data/guardrail_notifications.jsonl
VELEZ_NOTIFY_WEBHOOK_URL=
VELEZ_NOTIFY_DISCORD_WEBHOOK_URL=
VELEZ_NOTIFY_TELEGRAM_BOT_TOKEN=
VELEZ_NOTIFY_TELEGRAM_CHAT_ID=
VELEZ_NOTIFY_MIN_SEVERITY=warn
VELEZ_NOTIFY_COOLDOWN_SECONDS=1800
```

Notifications currently fire for lifecycle guardrails such as max positions exceeded, missing stops, orphan positions, and broker snapshot errors.
They also fire for lifecycle position-count changes and new Alpaca fill activity after the notification baseline is established.

To send a manual test from the authenticated dashboard API:

```bash
curl -fsS -u "$VELEZ_DASHBOARD_USERNAME:$VELEZ_DASHBOARD_PASSWORD" \
  -H "Content-Type: application/json" \
  -d '{"channel":"all"}' \
  "$VELEZ_PUBLIC_URL/api/notifications/test"
```

The same test is available from the Risk Command Center as `Test notifications`.

## 6. Exit Management

Use the Trade Lifecycle Command Center after positions are open:

- `Breakeven stops` moves eligible broker stops to entry only when a position is at or beyond `1R` and the stop has not reached breakeven. It requires the approval token.
- `Plan partials` returns advisory `25%`, `50%`, and full-close quantities. It never submits exit orders.
- `Position Doctor` groups each live position with its journal link, broker stop state, repair status, and claim candidates.
- `Auto-claim` attaches orphan broker positions to the best recent actionable journal decision for the same symbol/side. Manual claim buttons are shown when candidates exist.
- `Reduce plan` suggests guarded 25%, 50%, or 100% exposure reductions. Submitting a reduction requires the approval token and sends a paper market exit order for the selected symbol/fraction.
- Lifecycle `Needs action` summarizes stop moves, partial reviews, drawdown reviews, and guardrails.
- Telegram/file notifications fire once for lifecycle thresholds such as `1R`, `2R`, and drawdown review levels.

Breakeven stop movement cancels the existing broker stop for the symbol and submits a replacement paper stop at entry for the current position quantity. Stop repair submits a broker stop only when a linked journal stop is available; it will not invent a risk level. Exposure reduction cancels the selected symbol's broker stop orders before submitting the reduction market order, then returns a fresh lifecycle/scanner verification payload. Review Alpaca after any stop move, repair, or reduction.

The VPS scanner will not reopen auto-submit while lifecycle has critical action items, such as an unprotected open position. Set `VELEZ_SCANNER_PAUSE_ON_LIFECYCLE_CRITICAL=false` only for a deliberate operator override.

When exposure is full and lifecycle is otherwise clean, the bot sends an operator prompt with reduction ideas. Scanner reopen is allowed only when exposure is below max, lifecycle has no critical items, and the scanner is not operator-paused or otherwise blocked.

## 7. Go / No-Go

Go only when:

- Bot health is green or every warning is understood.
- Lifecycle guardrails are clear.
- Scanner and alert coverage are fresh enough for the trading plan.
- Approval mode matches the desired risk posture.

No-go when:

- Open positions exceed the configured cap.
- Any open position lacks stop protection.
- Alpaca paper connectivity is degraded.
- Dashboard auth or notification delivery is not ready for public operation.
