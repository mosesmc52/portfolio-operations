#!/usr/bin/env bash
set -euo pipefail

echo "[cron][alpaca-sync] $(date) starting"

# --- import container env ---
if [[ -r /proc/1/environ ]]; then
  while IFS= read -r -d '' kv; do
    export "$kv" || true
  done < /proc/1/environ
else
  echo "[cron][alpaca-sync][FATAL] cannot read /proc/1/environ" >&2
  exit 2
fi

APP_ROOT="/app"
cd "$APP_ROOT"
export PYTHONPATH="$APP_ROOT"

# --- required env ---
: "${DATABASE_URL:?missing DATABASE_URL}"
: "${DJANGO_SETTINGS_MODULE:=core.settings}"
export DJANGO_SETTINGS_MODULE

# --- required Alpaca env ---
: "${ALPACA_BASE_URL:?missing ALPACA_BASE_URL}"
: "${ALPACA_KEY_ID:?missing ALPACA_KEY_ID}"
: "${ALPACA_SECRET_KEY:?missing ALPACA_SECRET_KEY}"

# Defaults match your cron
FUND_ID="${FUND_ID:-1}"
DAYS="${ALPACA_SYNC_DAYS:-7}"
LIMIT="${ALPACA_SYNC_LIMIT:-500}"

echo "[cron][alpaca-sync] DATABASE_URL=${DATABASE_URL}"
echo "[cron][alpaca-sync] FUND_ID=${FUND_ID} DAYS=${DAYS} LIMIT=${LIMIT}"
echo "[cron][alpaca-sync] ALPACA_BASE_URL=${ALPACA_BASE_URL}"
echo "[cron][alpaca-sync] ALPACA_KEY_ID=set"
echo "[cron][alpaca-sync] ALPACA_SECRET_KEY=set"

# Wait up to 60s for lock (matches your cron)
exec flock -w 60 /tmp/operations_db.lock \
  /app/scripts/manage_wrapper.sh sync_alpaca_filled_orders_last_days \
    --fund-id="$FUND_ID" \
    --days="$DAYS" \
    --limit="$LIMIT"
