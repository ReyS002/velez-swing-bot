# Shared VWAP Engine

`core/vwap_engine.py` is the common market-price VWAP component used by Bull
Pilot, Velez Bot, and Velez Swing Bot. Independent deployment repositories
vendor the same verified source file so the trading services do not depend on a
sibling checkout at runtime. The engine has no broker, network, execution, or
order-submission dependency.

## What it calculates

- Session VWAP from completed bars: `sum(typical price × volume) / sum(volume)`,
  where typical price is `(high + low + close) / 3`.
- Optional weekly VWAP, with ISO-week reset.
- Optional manually supplied anchored VWAPs through `set_anchor(name, timestamp)`.
  Supported future anchor names include session/weekly/monthly open, earnings,
  swing high/low, gap, breakout, and a manual timestamp. Event detection is not
  assumed when the source metadata does not exist.
- Primary VWAP position, slope, raw/percentage/ATR distance, compression,
  extension, persistence, price cross, confirmed reclaim/loss, and confirmed
  bounce/rejection.

Equity defaults use America/New_York regular trading hours (09:30–16:00) and
exclude extended hours. Crypto 24/7 and futures session modes are supported by
configuration; zero-volume and out-of-session bars are marked unavailable,
not silently mixed into the calculation.

## Three levels

1. **Bias:** above/rising and below/falling are directional context; proximity,
   flatness, and repeated crossings are neutral/choppy context.
2. **Scoring:** every point has a named contribution and human-readable reason.
   The default values are configurable under `vwap.score`.
3. **Setup confluence:** an existing Velez/Bull setup is classified as premium,
   strong, moderate, neutral, or conflict using VWAP direction plus available
   SMA structure and relative-volume metadata. VWAP never creates a standalone
   entry.

The engine adds `vwap`, `vwap_score`, `vwap_confluence`, `vwap_score_reasons`,
and a compact `vwap_alert` string to a qualified strategy signal. It also
includes advisory trade-management context, but does not implement an exit.

## Safety boundary

`hard_filter_enabled` is **false** in all three shipped configurations. With
the shipped setting, the integration is informational/scoring-only: it does
not alter an entry, stop, target, exit, risk budget, position size, broker
endpoint, order route, or execution setting. An explicit future opt-in can
filter only a setup with confirmed opposite VWAP price-and-slope alignment; it
still cannot change sizing, exits, or broker behavior. A disabled VWAP
configuration leaves signal identity and order prices unchanged; this is
regression-tested per bot.

Bull Pilot's existing `execution_algorithm: vwap` remains a separate
institutional order-slicing label. It is not this market-price VWAP indicator
and was not changed.

## Bot defaults

| Bot | Primary reference | Supplemental reference |
|---|---|---|
| Bull Pilot | session VWAP | optional weekly / anchored |
| Velez Bot | session VWAP | optional weekly / anchored |
| Velez Swing Bot | weekly VWAP | session VWAP |

After a completed bar reaches the strategy engine, a read-only snapshot is
available at `GET /api/vwap?symbol=SPY`. The current signal/decision metadata
also carries the same context for journal, Mentor, Winston, and alert consumers.

## Configuration shape

```yaml
vwap:
  enabled: true
  bias_enabled: true
  scoring_enabled: true
  setup_confluence_enabled: true
  hard_filter_enabled: false
  session_vwap: true
  weekly_vwap: false
  anchored_vwap: false
  primary_variant: session
  score:
    above_vwap: 5
    aligned_slope: 3
    reclaim: 4
    bounce: 4
    rejection: 4
    excessive_extension_penalty: -3
```

Do not turn on a hard filter until it has a strategy-specific, out-of-sample
comparison and paper-forward evidence. A future enhancement can consume the
existing advisory exit context for optional trade management without changing
the current behavior.
