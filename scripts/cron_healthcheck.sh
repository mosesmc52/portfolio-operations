#!/usr/bin/env bash
set -euo pipefail

echo "[cron] $(date) starting healthcheck"

# -------------------------------------------------
# 1) Import full container environment (Docker env)
# -------------------------------------------------
if [[ -r /proc/1/environ ]]; then
  while IFS= read -r -d '' kv; do
    export "$kv" || true
  done < /proc/1/environ
else
  echo "[cron][ERROR] cannot read /proc/1/environ"
  exit 2
fi

# -------------------------------------------------
# 2) Deterministic working dir + python path
# -------------------------------------------------
APP_ROOT="/app"
cd "$APP_ROOT"
export PYTHONPATH="$APP_ROOT"

# -------------------------------------------------
# 3) Required environment validation
# -------------------------------------------------
REQUIRED_VARS=(
  DATABASE_URL
  DJANGO_SETTINGS_MODULE
)

missing=0

for v in "${REQUIRED_VARS[@]}"; do
  if [[ -z "${!v:-}" ]]; then
    echo "[cron][ERROR] missing env: $v"
    missing=1
  fi
done

if [[ "$missing" -eq 1 ]]; then
  echo "[cron][FATAL] required environment variables missing — aborting"
  env | sort
  exit 3
fi

# -------------------------------------------------
# 4) Helpful diagnostics (very useful for cron)
# -------------------------------------------------
echo "[cron] whoami=$(whoami)"
echo "[cron] pwd=$(pwd)"
echo "[cron] DATABASE_URL=$DATABASE_URL"
echo "[cron] PYTHONPATH=$PYTHONPATH"

# SQLite specific sanity
if [[ "$DATABASE_URL" == sqlite:* ]]; then
  DB_PATH="${DATABASE_URL#sqlite:////}"
  if [[ ! -f "$DB_PATH" ]]; then
    echo "[cron][ERROR] sqlite file missing: $DB_PATH"
    ls -la "$(dirname "$DB_PATH")" || true
    exit 4
  fi
fi

# -------------------------------------------------
# 5) Run actual command
# -------------------------------------------------
echo "[cron] executing manage.py healthcheck"
exec python manage.py healthcheck
