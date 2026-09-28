# Release Checklist

Use this for every Trading Bull Desk release.

## 1. Preflight

```bash
git status --short
git branch --show-current
python3 -m pytest bot/tests
```

Confirm:

- You are on the intended bot branch.
- Only bot-related files are staged.
- No raw `.env`, SQLite runtime databases, `.p8`, `.pem`, `.key`, `__pycache__`, or build output files are staged.
- The test suite passes.

## 2. Local Smoke

```bash
export VELEZ_EXECUTE_ORDERS=false
export VELEZ_DASHBOARD_AUTH_ENABLED=true
export VELEZ_DASHBOARD_USERNAME=desk
export VELEZ_DASHBOARD_PASSWORD=local-test-password
python3 -m bot.main --config bot/config.yaml webhook --host 127.0.0.1 --port 8080
```

In another shell:

```bash
curl -i http://127.0.0.1:8080/health
curl -i http://127.0.0.1:8080/dashboard
curl -fsS -u desk:local-test-password http://127.0.0.1:8080/api/bot/health
curl -fsS -u desk:local-test-password http://127.0.0.1:8080/api/scanner/status
```

Confirm:

- `/health` is public.
- `/dashboard` returns `401` without credentials.
- Authenticated dashboard APIs return JSON.
- Local execution is not armed unless you are intentionally testing paper order submission.

## 3. VPS Backup

On the VPS:

```bash
cd /opt/stacks/velez-trading-bot
./bot/deploy/vps_backup.sh
cp .env ".env.backup.$(date +%Y%m%d-%H%M%S)"
```

Confirm the backup includes the SQLite data directory and current environment file.

## 4. Deploy

On the VPS:

```bash
cd /opt/stacks/velez-trading-bot
docker compose --profile ai --profile voice up -d --build webhook
```

If dashboard auth is not already configured, add:

```text
VELEZ_DASHBOARD_AUTH_ENABLED=true
VELEZ_DASHBOARD_USERNAME=desk
VELEZ_DASHBOARD_PASSWORD=long-random-password
```

## 5. Post-Deploy Verification

```bash
export VELEZ_PUBLIC_URL="https://velezbot.72.62.169.3.nip.io"

curl -fsS "$VELEZ_PUBLIC_URL/health"
curl -i "$VELEZ_PUBLIC_URL/dashboard"
curl -fsS -u "$VELEZ_DASHBOARD_USERNAME:$VELEZ_DASHBOARD_PASSWORD" "$VELEZ_PUBLIC_URL/api/bot/health"
curl -fsS -u "$VELEZ_DASHBOARD_USERNAME:$VELEZ_DASHBOARD_PASSWORD" "$VELEZ_PUBLIC_URL/api/dashboard/state"
curl -fsS -u "$VELEZ_DASHBOARD_USERNAME:$VELEZ_DASHBOARD_PASSWORD" "$VELEZ_PUBLIC_URL/api/scanner/status"
curl -fsS -u "$VELEZ_DASHBOARD_USERNAME:$VELEZ_DASHBOARD_PASSWORD" "$VELEZ_PUBLIC_URL/api/lifecycle/state"
```

Confirm:

- Dashboard version is expected.
- Bot health is green or every warning is understood.
- Alpaca endpoint is paper.
- Execution mode matches the intended release mode.
- Scanner status matches config.
- Lifecycle guardrails are clear or intentionally handled.
- `/dashboard` challenges without credentials.

## 6. Rollback

If verification fails:

```bash
cd /opt/stacks/velez-trading-bot
docker compose logs --tail=200 webhook
git log --oneline -5
git switch <previous-known-good-branch-or-commit>
docker compose --profile ai --profile voice up -d --build webhook
```

Restore `.env` from the timestamped backup only if the failure came from environment changes.

