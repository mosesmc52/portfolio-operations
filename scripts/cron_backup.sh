#!/usr/bin/env bash
set -euo pipefail

echo "[cron][backup] $(date) starting"

# --- import container env ---
if [[ -r /proc/1/environ ]]; then
  while IFS= read -r -d '' kv; do
    export "$kv" || true
  done < /proc/1/environ
else
  echo "[cron][backup][FATAL] cannot read /proc/1/environ" >&2
  exit 2
fi

APP_ROOT="/app"
cd "$APP_ROOT"
export PYTHONPATH="$APP_ROOT"

# --- required env ---
: "${DATABASE_URL:?missing DATABASE_URL}"
: "${DJANGO_SETTINGS_MODULE:=core.settings}"
export DJANGO_SETTINGS_MODULE

# --- resolve sqlite path (for sanity checks) ---
DB_PATH=""
if [[ "${DATABASE_URL}" == sqlite:* ]]; then
  path="${DATABASE_URL#sqlite:}"
  if [[ "$path" == "////"* ]]; then
    DB_PATH="/${path#////}"
  elif [[ "$path" == "///"* ]]; then
    DB_PATH="${path#///}"
  else
    DB_PATH="$path"
  fi
fi

# Allow override (matches your CLI flag)
DB_PATH="${DB_PATH:-/data/operations.db}"

echo "[cron][backup] DATABASE_URL=${DATABASE_URL}"
echo "[cron][backup] db_path=${DB_PATH}"

# Fail loud if DB missing
if [[ ! -f "$DB_PATH" ]]; then
  echo "[cron][backup][FATAL] sqlite file missing: $DB_PATH" >&2
  ls -la "$(dirname "$DB_PATH")" >&2 || true
  exit 4
fi

# --- parameters (env override friendly) ---
PREFIX="${BACKUP_PREFIX:-backups/operations}"
FILENAME="${BACKUP_FILENAME:-operations}"
MAX_DAYS="${BACKUP_MAX_DAYS:-30}"
ACL="${BACKUP_ACL:-private}"

# gzip flag (default on)
GZIP_FLAG="--gzip"
if [[ "${BACKUP_GZIP:-1}" == "0" ]]; then
  GZIP_FLAG=""
fi

# --- run under lock (non-blocking, as your cron uses -n) ---
exec flock -n /tmp/operations_db.lock \
  /app/scripts/manage_wrapper.sh backup_operations_db \
    --db-path="$DB_PATH" \
    --prefix="$PREFIX" \
    --filename="$FILENAME" \
    --max-days="$MAX_DAYS" \
    $GZIP_FLAG \
    --acl="$ACL"
