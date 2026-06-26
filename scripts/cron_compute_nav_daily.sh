#!/usr/bin/env bash
set -euo pipefail

echo "[cron][nav-daily] $(date) starting"

if [[ -r /proc/1/environ ]]; then
  while IFS= read -r -d '' kv; do
    export "$kv" || true
  done < /proc/1/environ
else
  echo "[cron][nav-daily][FATAL] cannot read /proc/1/environ" >&2
  exit 2
fi

APP_ROOT="/app"
cd "$APP_ROOT"
export PYTHONPATH="$APP_ROOT"

: "${DATABASE_URL:?missing DATABASE_URL}"
: "${DJANGO_SETTINGS_MODULE:=core.settings}"
: "${ACCOUNT_CREDENTIALS_ENCRYPTION_KEY:?missing ACCOUNT_CREDENTIALS_ENCRYPTION_KEY}"
export DJANGO_SETTINGS_MODULE

AS_OF_DATE="${NAV_SNAPSHOT_AS_OF_DATE:-}"

echo "[cron][nav-daily] DATABASE_URL=${DATABASE_URL}"
echo "[cron][nav-daily] ACCOUNT_CREDENTIALS_ENCRYPTION_KEY=set"
if [[ -n "$AS_OF_DATE" ]]; then
  echo "[cron][nav-daily] AS_OF_DATE=${AS_OF_DATE}"
  exec flock -w 60 /tmp/operations_db.lock \
    /app/scripts/manage_wrapper.sh compute_nav \
      --all \
      --date="$AS_OF_DATE"
fi

exec flock -w 60 /tmp/operations_db.lock \
  /app/scripts/manage_wrapper.sh compute_nav \
    --all
