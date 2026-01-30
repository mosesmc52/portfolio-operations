#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/app"
cd "$APP_ROOT"

# Ensure Django project is importable under cron
export PYTHONPATH="${APP_ROOT}${PYTHONPATH:+:$PYTHONPATH}"

# Load runtime env explicitly (cron-safe)
if [[ -f "$APP_ROOT/.env.runtime" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$APP_ROOT/.env.runtime"
  set +a
fi

export PYTHONUNBUFFERED=1
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-core.settings}"
export DJANGO_CONFIGURATION="${DJANGO_CONFIGURATION:-Common}"

# Optional: serialize with other jobs touching sqlite
# (use same lock file across ALL sqlite-touching cron jobs)
exec flock -w 60 /tmp/operations_db.lock \
  /app/scripts/manage_wrapper.sh healthcheck
