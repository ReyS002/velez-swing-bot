#!/usr/bin/env bash
set -euo pipefail

# Bull Pilot Release Builder
# Usage:
#   ./make_release.sh --email user@example.com     # watermarked build for one user
#   ./make_release.sh --public                      # un-watermarked public release

VERSION="${VERSION:-1.0.0}"
BRAND="Bull Pilot"
BRAND_SLUG="bull-pilot"
ENV_PREFIX="BULLPILOT"

# ── Parse args ──────────────────────────────────────────────
EMAIL=""
PUBLIC=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --email) EMAIL="$2"; shift 2 ;;
        --public) PUBLIC=true; shift ;;
        --version) VERSION="$2"; shift 2 ;;
        *) echo "Unknown: $1"; exit 1 ;;
    esac
done

if [ "$PUBLIC" = false ] && [ -z "$EMAIL" ]; then
    echo "ERROR: pass --email user@example.com or --public"
    exit 1
fi

# ── Paths ───────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="/tmp/${BRAND_SLUG}-build-$$"
OUTPUT_DIR="${REPO_ROOT}/dist"
mkdir -p "$OUTPUT_DIR"

# ── License ID ──────────────────────────────────────────────
LICENSE_ID="BP-$(date +%Y%m%d)-$(openssl rand -hex 4 | tr '[:lower:]' '[:upper:]')"

if [ "$PUBLIC" = true ]; then
    ZIP_NAME="${BRAND_SLUG}-v${VERSION}.zip"
    WATERMARK_LINE="# ${BRAND} v${VERSION} — Personal Use License"
else
    SAFE_EMAIL=$(echo "$EMAIL" | sed 's/[^a-zA-Z0-9._-]/_/g')
    ZIP_NAME="${BRAND_SLUG}-v${VERSION}-${SAFE_EMAIL}.zip"
    WATERMARK_LINE="# Licensed to: ${EMAIL}"
fi

echo "🔨 Building ${BRAND} v${VERSION}"
echo "   License ID: ${LICENSE_ID}"
[ "$PUBLIC" = false ] && echo "   Licensee:   ${EMAIL}"
echo "   Output:     ${OUTPUT_DIR}/${ZIP_NAME}"

# ── Copy source tree ────────────────────────────────────────
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/${BRAND_SLUG}"

# Copy bot/ directory (the distributable package)
rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='.DS_Store' \
      --exclude='.env' --exclude='*.bak' \
      "$REPO_ROOT/bot/" "$BUILD_DIR/${BRAND_SLUG}/"

# Copy deploy support files into the package root
cp "$REPO_ROOT/bot/deploy/requirements-webhook.txt" "$BUILD_DIR/${BRAND_SLUG}/"
cp "$REPO_ROOT/bot/deploy/docker-compose.yml" "$BUILD_DIR/${BRAND_SLUG}/"
cp "$REPO_ROOT/bot/deploy/Dockerfile.webhook" "$BUILD_DIR/${BRAND_SLUG}/"

# ── Rename VELEZ → BULLPILOT in all files ──────────────────
echo "   Renaming VELEZ → ${ENV_PREFIX}..."

find "$BUILD_DIR/${BRAND_SLUG}" -type f \( \
    -name '*.py' -o -name '*.yaml' -o -name '*.yml' \
    -o -name '*.pine' -o -name '*.md' -o -name '*.sh' \
    -o -name '*.txt' -o -name '*.example' \
\) -exec sed -i \
    -e "s/VELEZ_/${ENV_PREFIX}_/g" \
    -e 's/velez_strategy/bullpilot_strategy/g' \
    -e 's/velez_lot_sizing/bullpilot_lot_sizing/g' \
    -e 's/velez_core_alerts/bullpilot_alerts/g' \
    -e 's/velez-trading-bot/bull-pilot/g' \
    -e 's/velezbot\./bullpilot./g' \
    -e 's/VelezInstitutionalStrategy/BullPilotStrategy/g' \
    -e 's/velez_buy_setup/bullpilot_buy_setup/g' \
    -e 's/velez_sell_setup/bullpilot_sell_setup/g' \
    -e 's/velez-watchlist-scanner/bullpilot-watchlist-scanner/g' \
    -e "s|Trading Bull Desk|${BRAND}|g" \
    -e 's|Oliver Velez|Velez Institutional|g' \
    {} +

# ── Rename files ────────────────────────────────────────────
echo "   Renaming strategy files..."
mv "$BUILD_DIR/${BRAND_SLUG}/core/velez_strategy.py" \
   "$BUILD_DIR/${BRAND_SLUG}/core/bullpilot_strategy.py" 2>/dev/null || true
mv "$BUILD_DIR/${BRAND_SLUG}/core/velez_lot_sizing.py" \
   "$BUILD_DIR/${BRAND_SLUG}/core/bullpilot_lot_sizing.py" 2>/dev/null || true
mv "$BUILD_DIR/${BRAND_SLUG}/tradingview/velez_core_alerts.pine" \
   "$BUILD_DIR/${BRAND_SLUG}/tradingview/bullpilot_alerts.pine" 2>/dev/null || true

# Rename test files
for old in "$BUILD_DIR/${BRAND_SLUG}/tests"/test_velez_*.py; do
    [ -f "$old" ] || continue
    new=$(echo "$old" | sed 's/test_velez_/test_bullpilot_/')
    mv "$old" "$new"
done

# Fix imports in renamed test files
find "$BUILD_DIR/${BRAND_SLUG}/tests" -name 'test_bullpilot_*.py' -exec sed -i \
    -e 's/from bot\.core\.velez_strategy/from bot.core.bullpilot_strategy/g' \
    -e 's/test_velez_/test_bullpilot_/g' \
    {} +

# ── Inject watermark ────────────────────────────────────────
ENV_FILE="$BUILD_DIR/${BRAND_SLUG}/.env.example"
if [ -f "$ENV_FILE" ]; then
    WATERMARK=$(cat <<WATERMARK
# ============================================================
# ${BRAND} v${VERSION}
${WATERMARK_LINE}
# License ID: ${LICENSE_ID}
# Personal use only. Redistribution prohibited.
# ============================================================

WATERMARK
)
    echo "$WATERMARK$(cat "$ENV_FILE")" > "$ENV_FILE.tmp"
    mv "$ENV_FILE.tmp" "$ENV_FILE"
fi

# Also watermark a hidden license tracker in __init__.py
INIT_FILE="$BUILD_DIR/${BRAND_SLUG}/__init__.py"
if [ "$PUBLIC" = false ]; then
    echo "# _license_id: ${LICENSE_ID}" >> "$INIT_FILE"
    echo "# _licensee: ${EMAIL}" >> "$INIT_FILE"
fi

# ── Copy LICENSE ────────────────────────────────────────────
cp "$REPO_ROOT/LICENSE" "$BUILD_DIR/${BRAND_SLUG}/LICENSE.txt" 2>/dev/null || true

# ── Add a friendly README ──────────────────────────────────
cat > "$BUILD_DIR/${BRAND_SLUG}/README.txt" << 'README'
BULL PILOT — Personal Trading Bot
==================================

QUICK START (no accounts needed):
  1. pip install -r requirements-webhook.txt
  2. python -m bot.main --config bot/config.yaml webhook --host 127.0.0.1 --port 8080
  3. Open http://127.0.0.1:8080/dashboard

That's it — the bot auto-detects no Alpaca keys and runs in
simulated paper mode with $100k virtual cash and live prices
from Yahoo Finance (free, no API key required).

WITH ALPACA PAPER (optional):
  1. cp .env.example .env
  2. Add your APCA_API_KEY_ID + APCA_API_SECRET_KEY
  3. Restart the bot — it automatically switches to Alpaca

SCANNER MODE (no TradingView alerts needed):
  Edit bot/config.yaml → scanner.enabled: true, add your symbols.
  The bot polls for setups automatically.

Paper trading only. See LICENSE.txt for terms.
README

# ── Zip it ─────────────────────────────────────────────────
cd "$BUILD_DIR"
zip -qr "${OUTPUT_DIR}/${ZIP_NAME}" "${BRAND_SLUG}/"
cd "$REPO_ROOT"

# ── Cleanup ─────────────────────────────────────────────────
rm -rf "$BUILD_DIR"

# ── Summary ─────────────────────────────────────────────────
ZIP_SIZE=$(du -h "${OUTPUT_DIR}/${ZIP_NAME}" | cut -f1)
echo ""
echo "✅ ${BRAND} v${VERSION} built"
echo "   File: ${OUTPUT_DIR}/${ZIP_NAME}"
echo "   Size: ${ZIP_SIZE}"
echo "   ID:   ${LICENSE_ID}"
