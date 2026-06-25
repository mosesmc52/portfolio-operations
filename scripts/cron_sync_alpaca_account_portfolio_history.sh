#!/usr/bin/env bash
set -euo pipefail

echo "[cron][alpaca-history] $(date) starting"

if [[ -r /proc/1/environ ]]; then
  while IFS= read -r -d '' kv; do
    export "$kv" || true
  done < /proc/1/environ
else
  echo "[cron][alpaca-history][FATAL] cannot read /proc/1/environ" >&2
  exit 2
fi

APP_ROOT="/app"
cd "$APP_ROOT"
export PYTHONPATH="$APP_ROOT"

: "${DATABASE_URL:?missing DATABASE_URL}"
: "${DJANGO_SETTINGS_MODULE:=core.settings}"
: "${ACCOUNT_CREDENTIALS_ENCRYPTION_KEY:?missing ACCOUNT_CREDENTIALS_ENCRYPTION_KEY}"
export DJANGO_SETTINGS_MODULE

PERIOD="${ALPACA_PORTFOLIO_HISTORY_PERIOD:-1A}"

echo "[cron][alpaca-history] DATABASE_URL=${DATABASE_URL}"
echo "[cron][alpaca-history] PERIOD=${PERIOD}"
echo "[cron][alpaca-history] ACCOUNT_CREDENTIALS_ENCRYPTION_KEY=set"

exec flock -w 60 /tmp/operations_db.lock \
  /app/scripts/manage_wrapper.sh sync_alpaca_account_portfolio_history \
    --all \
    --period="$PERIOD"
