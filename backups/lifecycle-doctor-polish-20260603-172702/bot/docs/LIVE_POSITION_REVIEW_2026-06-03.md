# Live Paper Position Review - 2026-06-03

This review is operational context for the Alpaca paper account, not financial advice.

## Snapshot

Checked after the V6.21 dashboard-auth deployment on June 3, 2026.

Account state from `/api/dashboard/state` and `/api/lifecycle/state`:

- Open paper positions: `4`
- Configured max open positions: `3`
- Open orders: `0`
- Lifecycle guardrails: `5`
- Open risk: `$0.00` because no linked stops were found
- Average R multiple: unavailable because entry/stop/current-price math is incomplete without stops

## Open Positions

| Symbol | Side | Quantity | Avg Entry | Current At Review | Unrealized P/L At Review | Lifecycle Finding |
|---|---:|---:|---:|---:|---:|---|
| `BTC` | short | `1` | `30.48` | `29.33` | `+1.15` | Missing broker/journal stop |
| `HIMS` | long | `355` | `27.77` | `27.26` | `-181.05` | Missing broker/journal stop |
| `HOOD` | long | `292` | `89.94` | `86.93` | `-878.04` | Missing broker/journal stop |
| `NVDA` | long | `188` | `219.68` | `221.35` | `+314.46` | Missing broker/journal stop |

## Guardrail Read

The bot is behaving correctly by blocking new paper entries while open positions exceed the configured cap. Current guardrails are:

- `max_positions_exceeded`: 4 positions open; configured max is 3.
- `missing_stop` on each open position.

The most important cleanup item is stop protection. Without broker or journal stops, the lifecycle engine cannot compute R multiple, open risk, or management progression.

## Operator Actions

Recommended operating posture:

- Keep paper order approval required until positions are back within policy and stops are visible.
- Add/repair stop protection for any position intentionally kept open.
- Manually close or reduce paper positions only after reviewing the Alpaca paper account and intended training scenario.
- Re-run `/api/lifecycle/state` after any manual broker change.

The bot should not auto-close these positions without explicit operator instruction.

