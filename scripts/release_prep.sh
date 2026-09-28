#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"
${ROOT_DIR}/.venv/bin/python -m compileall webhook_server.py core journal_store.py brokers >/tmp/velez-compileall.log
${ROOT_DIR}/.venv/bin/python -m pytest -q tests --import-mode=importlib
${ROOT_DIR}/.venv/bin/python scripts/velez_smoke.py --base-url "${VELEZ_BASE_URL:-http://127.0.0.1:8080}" ${VELEZ_OPS_TOKEN:+--token "$VELEZ_OPS_TOKEN"}
