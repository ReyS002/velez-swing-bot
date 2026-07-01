#!/usr/bin/env bash
set -euo pipefail

ROOT_URL="${VELEZ_PUBLIC_URL:-}"
if [[ -z "${ROOT_URL}" ]]; then
  HOST="${VELEZ_PUBLIC_HOST:-velezbot.72.62.169.3.nip.io}"
  ROOT_URL="https://${HOST}"
fi
ROOT_URL="${ROOT_URL%/}"

curl -fsS "${ROOT_URL}/health" >/dev/null
curl -fsS "${ROOT_URL}/api/bot/health" >/dev/null
curl -fsS "${ROOT_URL}/api/alerts/coverage" >/dev/null

echo "Trading Bull Desk health check passed: ${ROOT_URL}"
