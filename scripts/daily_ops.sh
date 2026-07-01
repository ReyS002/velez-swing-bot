#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_URL="${VELEZ_BASE_URL:-http://127.0.0.1:8080}"
TOKEN="${VELEZ_OPS_TOKEN:-${VELEZ_OPS_OWNER_TOKEN:-}}"
python3 "${ROOT_DIR}/scripts/velez_smoke.py" --base-url "${BASE_URL}" ${TOKEN:+--token "$TOKEN"}
