#!/usr/bin/env bash
set -euo pipefail

STACK_ROOT="${VELEZ_STACK_ROOT:-/opt/stacks/velez-trading-bot}"
BACKUP_DIR="${VELEZ_BACKUP_DIR:-${STACK_ROOT}/data/backups}"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
ARCHIVE="${BACKUP_DIR}/trading-bull-desk-${STAMP}.tar.gz"

mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}" || true

cd "${STACK_ROOT}"

items=()
for path in \
  ".env" \
  ".env.example" \
  "docker-compose.yml" \
  "bot/config.yaml" \
  "bot/tradingview/velez_core_alerts.pine" \
  "bot/docs/FIRST_TIMER_GUIDE.md" \
  "bot/docs/VPS_DEPLOYMENT.md" \
  "data/trading_bull_desk.sqlite3" \
  "data/trading_bull_desk.sqlite3-wal" \
  "data/trading_bull_desk.sqlite3-shm"; do
  if [[ -e "${path}" ]]; then
    items+=("${path}")
  fi
done

if [[ "${#items[@]}" -eq 0 ]]; then
  echo "No Trading Bull Desk backup items found under ${STACK_ROOT}" >&2
  exit 1
fi

tar -czf "${ARCHIVE}" "${items[@]}"
chmod 600 "${ARCHIVE}" || true

find "${BACKUP_DIR}" -name "trading-bull-desk-*.tar.gz" -type f -mtime +14 -delete

echo "${ARCHIVE}"
