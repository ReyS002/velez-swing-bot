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
curl -fsS -u "$VELEZ_DASHBOARD_USERNAME:$VELEZ_DASHBOARD_PASSWORD" "$VELEZ_PUBLIC_URL/api/alerts/coverage"
```

Confirm:

- Scanner is running.
- Last scan time is fresh.
- `pause.paused` is false unless max exposure is intentionally reached.
- `today.counts` shows the scanner's submitted/proposed/diagnostic/rejected mix for the session.
- Skipped lanes are understood.
- TradingView coverage has no unexpected stale or never-seen symbols.
- Futures lanes are either configured with Polygon or intentionally disabled.

When `pause.paused=true` with `reason=max_exposure_reached`, the VPS scanner is intentionally calm: it stops looking for new entries until broker positions/open orders/staged exposure drop below the configured max-position cap. Per-symbol rejected signals also enter a cooldown window so the journal is not flooded with repeated same-symbol rejects.

Scanner operator controls are available from the dashboard and authenticated API:

- `POST /api/scanner/mode` with `mode=auto_submit`, `diagnostic`, or `paused` plus the approval token.
- `POST /api/scanner/orders/cancel-stale` with the approval token to cancel orphan scanner entry orders only.
- Exposure details list positions, open orders, and staged approvals that count toward the scanner cap.
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

## 6. Go / No-Go

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
