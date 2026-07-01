# Live Paper Position Actions - 2026-06-03

This is an operational paper-trading log, not financial advice.

## Actions Submitted

The operator requested:

- close paper losers,
- add stops to paper winners where possible,
- re-enable auto-submit paper mode,
- keep the existing approval-mode toggle available.

Submitted Alpaca paper orders:

| Symbol | Previous State | Action | Order Type | Quantity | Stop Price | Status At Verification |
|---|---|---|---|---:|---:|---|
| `BTC` | winning short | Add breakeven protective stop | buy stop | `1` | `30.48` | `new` |
| `HIMS` | losing long | Close position | sell market | `355` | n/a | `new` |
| `HOOD` | losing long | Close position | sell market | `292` | n/a | `new` |
| `NVDA` | winning long | Add breakeven protective stop | sell stop | `188` | `219.68` | `new` |

## Mode Change

The VPS was switched back to auto-submit paper mode:

```text
VELEZ_REQUIRE_ORDER_APPROVAL=false
```

The dashboard already includes an Approval Gate toggle in the Risk panel. It uses `/api/risk/approval-mode` and requires the local approval token from the Winston phone panel.

## Verification Snapshot

After the actions:

- `execution_armed`: `true`
- `approval_required`: `false`
- `open_positions`: `4`
- `open_orders`: `4`
- `guardrails`: `3`
- BTC stop source: `broker_open_order`
- NVDA stop source: `broker_open_order`
- HIMS and HOOD still show `missing_stop` until their close orders fill

The HIMS and HOOD market close orders were accepted by Alpaca paper but remained open at verification. Lifecycle will continue to show the position cap and missing-stop guardrails until those market orders fill and the positions disappear from Alpaca.

## Follow-Up Cleanup

After market open, the paper account had new auto-submitted short exposure and stale/orphan open orders. Cleanup actions completed from the VPS:

- Canceled stale/protective/orphan orders for `AMD`, `HIMS`, `TQQQ`, `MSFT`, `SPY`, and the stale `NVDA` sell-limit OTO.
- Closed losing paper shorts with market buy-to-close orders: `AMD`, `HIMS`, and `TQQQ`.
- Kept protective buy stops on the remaining paper shorts: `BTC`, `IWM`, and `NVDA`.
- Added diagnostic lifecycle reconciliation records for the remaining broker-protected positions so lifecycle links reflect the live paper account without pretending the bot submitted those entries.

Final verification snapshot:

- `open_positions`: `3`
- `open_orders`: `3`
- `guardrails`: `0`
- `open_risk`: `$232.70`
- `average_r_multiple`: approximately `0.25R`
- Remaining positions: `BTC` short with breakeven stop, `IWM` short with broker stop, `NVDA` short with broker stop

Code hardening deployed after cleanup:

- Lifecycle no longer links rejected journal decisions to live positions.
- Paper submission guard now counts current positions plus open/staged broker exposure before allowing a new auto-submit, reducing same-scan max-position overfills.
