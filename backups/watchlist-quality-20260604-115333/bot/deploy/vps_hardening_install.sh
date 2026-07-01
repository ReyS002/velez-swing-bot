#!/usr/bin/env bash
set -euo pipefail

STACK_ROOT="${VELEZ_STACK_ROOT:-/opt/stacks/velez-trading-bot}"
SCRIPT_DIR="${STACK_ROOT}/scripts"
BACKUP_SOURCE="${STACK_ROOT}/bot/deploy/vps_backup.sh"
HEALTH_SOURCE="${STACK_ROOT}/bot/deploy/vps_healthcheck.sh"

mkdir -p "${SCRIPT_DIR}" "${STACK_ROOT}/data/backups"
cp "${BACKUP_SOURCE}" "${SCRIPT_DIR}/backup_trading_bull_desk.sh"
cp "${HEALTH_SOURCE}" "${SCRIPT_DIR}/healthcheck_trading_bull_desk.sh"
chmod 700 "${SCRIPT_DIR}/backup_trading_bull_desk.sh" "${SCRIPT_DIR}/healthcheck_trading_bull_desk.sh"

if command -v docker >/dev/null 2>&1; then
  docker update --restart unless-stopped velez-trading-bot-webhook >/dev/null 2>&1 || true
fi

cron_line="17 4 * * * VELEZ_STACK_ROOT=${STACK_ROOT} ${SCRIPT_DIR}/backup_trading_bull_desk.sh >/tmp/trading-bull-desk-backup.log 2>&1"
existing="$(crontab -l 2>/dev/null || true)"
if ! printf "%s\n" "${existing}" | grep -Fq "backup_trading_bull_desk.sh"; then
  (printf "%s\n" "${existing}"; printf "%s\n" "${cron_line}") | crontab -
fi

"${SCRIPT_DIR}/backup_trading_bull_desk.sh" >/dev/null

echo "Trading Bull Desk VPS hardening installed under ${SCRIPT_DIR}"
