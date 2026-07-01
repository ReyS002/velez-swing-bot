# Safety & Failure Modes

**Disclaimer:** Educational use only. Not financial advice.

## Built-in Safeguards
- Default to paper trading
- Live trading requires **both**:
  - `enable_live_trading: true` in `config.yaml`
  - `ENABLE_LIVE_TRADING=true` environment variable
- TradingView/Alpaca webhook order submission requires **both**:
  - `webhook.execute_orders: true` or `--execute`
  - `VELEZ_EXECUTE_ORDERS=true`
- Webhook execution is paper-only by default and rejects non-paper Alpaca endpoints
- TradingView webhooks require `VELEZ_WEBHOOK_SECRET`
- Max daily loss and max consecutive losses
- Max open positions and max leverage
- Circuit breaker on volatility spikes (ATR%)
- Kill switch after repeated API errors (configurable)
- Slippage and commission modeling in backtests
- Price sanity checks (max stop distance %)
- Velez location gate: Elephant, 180, and Tail plays are No-Trade unless they occur at/near the 20 SMA, extended from the 20 SMA, or at/near the 200 SMA as required by the play
- No-chase gate: setups that move past trigger by more than 5% of body length are converted to limit pullback entries

## Known Risks
- **Data quality:** minute data from public sources can be incomplete.
- **Session alignment:** equities are filtered to RTH only; futures use CSV.
- **Order simulation:** intrabar fill ordering is conservative but still an approximation.
- **Latency & API errors:** live integrations can fail or return stale data.

## Suggested Mitigations
- Use high-quality data for backtests and validation
- Run a full paper-trade period before considering live trading
- Add broker-side risk controls (max order size, daily loss limits)
- Monitor logs and decision traces for unexpected behavior
