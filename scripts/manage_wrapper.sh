#!/usr/bin/env bash
set -euo pipefail

# ----------------------------------------
# Environment bootstrap
# ----------------------------------------

APP_ROOT="/app"
cd "$APP_ROOT"

# Ensure project root is importable (cron-safe)
# This fixes "No module named 'core'" under cron.
export PYTHONPATH="${APP_ROOT}${PYTHONPATH:+:$PYTHONPATH}"

# Load runtime env explicitly (cron-safe)
if [[ -f "$APP_ROOT/.env.runtime" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$APP_ROOT/.env.runtime"
  set +a
fi

# Sensible defaults
export PYTHONUNBUFFERED=1
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-core.settings}"
export DJANGO_CONFIGURATION="${DJANGO_CONFIGURATION:-Common}"

# Optional: make sqlite more tolerant under concurrency
# Django uses this for sqlite connections (seconds).
export SQLITE_BUSY_TIMEOUT="${SQLITE_BUSY_TIMEOUT:-30}"

# ----------------------------------------
# Quick sanity checks (fail loud)
# ----------------------------------------

# Make sure manage.py exists in expected location
if [[ ! -f "$APP_ROOT/manage.py" ]]; then
  echo "[FATAL] manage.py not found at $APP_ROOT/manage.py (pwd=$(pwd))" >&2
  ls -la "$APP_ROOT" >&2 || true
  exit 2
fi

# If you’re using sqlite at /data/operations.db, catch corrupt/truncated file early
DB_PATH="${DJANGO_DB_PATH:-/data/operations.db}"
if [[ -e "$DB_PATH" && ! -s "$DB_PATH" ]]; then
  echo "[FATAL] SQLite DB exists but is 0 bytes: $DB_PATH" >&2
  ls -la "$(dirname "$DB_PATH")" >&2 || true
  exit 3
fi

# ----------------------------------------
# Execution
# ----------------------------------------

exec python manage.py "$@"
