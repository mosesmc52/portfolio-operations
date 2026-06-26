#!/usr/bin/env bash
set -euo pipefail

echo "[cron][weekly-report] $(date) starting"

# --- import container env ---
if [[ -r /proc/1/environ ]]; then
  while IFS= read -r -d '' kv; do
    export "$kv" || true
  done < /proc/1/environ
else
  echo "[cron][weekly-report][FATAL] cannot read /proc/1/environ" >&2
  exit 2
fi

APP_ROOT="/app"
cd "$APP_ROOT"
export PYTHONPATH="$APP_ROOT"

# ============================================================
# Required core env
# ============================================================
: "${DATABASE_URL:?missing DATABASE_URL}"
: "${DJANGO_SETTINGS_MODULE:=core.settings}"
export DJANGO_SETTINGS_MODULE

# ============================================================
# SES / Email config
# ============================================================

USE_SES_EMAIL="${USE_SES_EMAIL:-true}"
AWS_SES_USE_V2="${AWS_SES_USE_V2:-true}"
DEFAULT_FROM_EMAIL="${DEFAULT_FROM_EMAIL:-noreply@example.com}"
AWS_SES_REGION_NAME="${AWS_SES_REGION_NAME:-us-east-1}"

: "${AWS_SES_ACCESS_KEY_ID:?missing AWS_SES_ACCESS_KEY_ID}"
: "${AWS_SES_SECRET_ACCESS_KEY:?missing AWS_SES_SECRET_ACCESS_KEY}"

# ============================================================
# OpenAI config
# ============================================================

: "${OPENAI_API_KEY:?missing OPENAI_API_KEY}"
OPENAI_MODEL="${OPENAI_MODEL:-gpt-5.2}"

# ============================================================
# Job parameters
# ============================================================

BENCH="${MONTHLY_BENCHMARK_SYMBOL:-SPY}"
SUBJECT_PREFIX="${MONTHLY_SUBJECT_PREFIX:-[Weekly Report] }"
FUND_ID="${FUND_ID:-1}"

echo "[cron][weekly-report] DATABASE_URL=${DATABASE_URL}"
echo "[cron][weekly-report] benchmark=${BENCH}"
echo "[cron][weekly-report] subject_prefix=${SUBJECT_PREFIX}"
echo "[cron][weekly-report] USE_SES_EMAIL=${USE_SES_EMAIL}"
echo "[cron][weekly-report] AWS_SES_USE_V2=${AWS_SES_USE_V2}"
echo "[cron][weekly-report] DEFAULT_FROM_EMAIL=${DEFAULT_FROM_EMAIL}"
echo "[cron][weekly-report] AWS_SES_REGION_NAME=${AWS_SES_REGION_NAME}"
echo "[cron][weekly-report] AWS_SES_ACCESS_KEY_ID=set"
echo "[cron][weekly-report] AWS_SES_SECRET_ACCESS_KEY=set"
echo "[cron][weekly-report] OPENAI_MODEL=${OPENAI_MODEL}"
echo "[cron][weekly-report] OPENAI_API_KEY=set"
echo "[cron][weekly-report] FUND_ID=${FUND_ID}"

exec flock -n /tmp/operations_db.lock \
  /app/scripts/manage_wrapper.sh run_monthly_reporting_workflow \
    --benchmark="$BENCH" \
    --fund-id="$FUND_ID" \
    --subject-prefix="$SUBJECT_PREFIX"
