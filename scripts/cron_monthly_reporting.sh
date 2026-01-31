#!/usr/bin/env bash
set -euo pipefail

echo "[cron][monthly] $(date) starting"

# --- import container env ---
if [[ -r /proc/1/environ ]]; then
  while IFS= read -r -d '' kv; do
    export "$kv" || true
  done < /proc/1/environ
else
  echo "[cron][monthly][FATAL] cannot read /proc/1/environ" >&2
  exit 2
fi

APP_ROOT="/app"
cd "$APP_ROOT"
export PYTHONPATH="$APP_ROOT"

# --- required env ---
: "${DATABASE_URL:?missing DATABASE_URL}"
: "${DJANGO_SETTINGS_MODULE:=core.settings}"
export DJANGO_SETTINGS_MODULE

BENCH="${MONTHLY_BENCHMARK_SYMBOL:-SPY}"
SUBJECT_PREFIX="${MONTHLY_SUBJECT_PREFIX:-[Monthly Report] }"

echo "[cron][monthly] DATABASE_URL=${DATABASE_URL}"
echo "[cron][monthly] benchmark=${BENCH}"
echo "[cron][monthly] subject_prefix=${SUBJECT_PREFIX}"

# --- run under lock (non-blocking, as your cron uses -n) ---
exec flock -n /tmp/operations_db.lock \
  /app/scripts/manage_wrapper.sh run_monthly_reporting_workflow \
    --async \
    --benchmark-symbol="$BENCH" \
    --subject-prefix="$SUBJECT_PREFIX"
