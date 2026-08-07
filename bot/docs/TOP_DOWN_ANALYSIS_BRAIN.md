# Top-Down Analysis Brain

Purpose: give every Trading Bull bot the same market-context brain before it decides how much trust to place in a setup.

## What it reads

- Daily and weekly bias from SPY, QQQ, and IWM.
- Breadth confirmation: at least 2 of 3 index proxies should agree for a supportive or hostile read.
- Sector leadership/laggard flow from the bot's configured correlation sector groups.
- Existing strategy context: setup/play, side, signal timeframe, and higher-timeframe confluence.

## What it returns

- `daily_bias` and `weekly_bias`: bullish, bearish, neutral, or unknown.
- `breadth`: supportive, hostile, mixed, or unknown.
- `sector_leadership`: ranked leaders and laggards from configured groups.
- `regime`: risk-on trend, risk-off trend, mixed/transition, or selective.
- `strategy_activation`: active, starter, watch, or inactive, with a size multiplier.
- `readback`: plain-English explanation for Winston/Mentor.

## Guardrail philosophy

Default mode is `advisory`. Advisory mode does not remove Oliver/Velez setups. It explains whether the market wind is helping or fighting and journals that evidence. If the owner wants stronger behavior later:

- `size`: keep the setup available but reduce size when context is opposed.
- `gate`: reject inactive context mismatches.

## Bot profiles

- Bull Pilot: evidence-gated and institutional-aware; default is advisory until live paper evidence proves stricter gates.
- Velez intraday: fast execution context; keeps 2m/5m/15m and 60m/240m confluence, adds daily/weekly/breadth/sector readback.
- Velez Swing: daily/weekly wind matters more because trades hold longer; same resources, slower weighting.

## Winston/Mentor explanation pattern

“This setup is valid because the signal timeframe agrees with higher timeframes, daily bias, weekly bias, SPY/QQQ/IWM breadth, and sector flow.”

If any source is stale or missing, Winston must say what is missing instead of pretending the setup has full confirmation.
