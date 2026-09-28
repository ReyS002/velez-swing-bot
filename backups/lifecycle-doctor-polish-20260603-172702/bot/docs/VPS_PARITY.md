# VPS Parity Checklist

Use this checklist before and after deploying Trading Bull Desk changes to the VPS.

## Public Endpoint Baseline

Run these from your local machine:

```bash
export VELEZ_PUBLIC_URL="https://velezbot.72.62.169.3.nip.io"

curl -fsS "$VELEZ_PUBLIC_URL/health"
curl -fsS -u "$VELEZ_DASHBOARD_USERNAME:$VELEZ_DASHBOARD_PASSWORD" "$VELEZ_PUBLIC_URL/api/bot/health"
curl -fsS -u "$VELEZ_DASHBOARD_USERNAME:$VELEZ_DASHBOARD_PASSWORD" "$VELEZ_PUBLIC_URL/api/dashboard/state"
curl -fsS -u "$VELEZ_DASHBOARD_USERNAME:$VELEZ_DASHBOARD_PASSWORD" "$VELEZ_PUBLIC_URL/api/scanner/status"
curl -fsS -u "$VELEZ_DASHBOARD_USERNAME:$VELEZ_DASHBOARD_PASSWORD" "$VELEZ_PUBLIC_URL/api/lifecycle/state"
```

Expected baseline:

- `/health` returns `ok: true`.
- `dashboard_version` matches local `DASHBOARD_VERSION`.
- `execution_armed` matches the intended paper-trading mode.
- `paper_endpoint` is true and Alpaca status is connected.
- `scanner.enabled` and `scanner.running` match `bot/config.yaml`.
- Futures lanes may show `polygon_key_missing` until `POLYGON_API_KEY` is configured.
- Lifecycle guardrails are clear or intentionally understood.

## Local To VPS File Parity

If SSH access is available:

```bash
ssh srv1668095.hstgr.cloud 'cd /opt/stacks/velez-trading-bot && sha256sum bot/config.yaml bot/webhook_server.py bot/static/dashboard/app.js bot/static/dashboard/styles.css bot/static/dashboard/index.html'
shasum -a 256 bot/config.yaml bot/webhook_server.py bot/static/dashboard/app.js bot/static/dashboard/styles.css bot/static/dashboard/index.html
```

Compare hashes for files that should be identical. Runtime-only files under `/app/data` should not match local development state and should not be committed.

## Auth Parity

Dashboard authentication should be enabled on any public VPS:

```text
VELEZ_DASHBOARD_AUTH_ENABLED=true
VELEZ_DASHBOARD_USERNAME=desk
VELEZ_DASHBOARD_PASSWORD=long-random-password
```

Expected behavior:

- `curl -i "$VELEZ_PUBLIC_URL/dashboard"` returns `401` without credentials.
- `curl -i -u "$VELEZ_DASHBOARD_USERNAME:$VELEZ_DASHBOARD_PASSWORD" "$VELEZ_PUBLIC_URL/dashboard"` returns `200`.
- `curl -i "$VELEZ_PUBLIC_URL/health"` remains `200` without credentials.
- TradingView webhook routes still require the separate webhook secret.

## Current Public Check From June 3, 2026

The public VPS reported:

- Dashboard version: `v6.21`
- Bot health: green
- Alpaca paper: connected
- Execution mode: armed for paper
- Scanner: active
- Futures scanner lanes: skipped when Polygon key is missing
- Open positions exceeded `max_open_positions`, causing a BTC scanner decision to reject with `max_open_positions`

