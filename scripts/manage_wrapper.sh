#!/usr/bin/env bash
set -euo pipefail

# ----------------------------------------
# Environment bootstrap
# ----------------------------------------

APP_ROOT="/app"
cd "$APP_ROOT"

# Load runtime env explicitly (cron-safe)
if [[ -f "$APP_ROOT/.env.runtime" ]]; then
  set -a
  source "$APP_ROOT/.env.runtime"
  set +a
fi

# Sensible defaults
export PYTHONUNBUFFERED=1
export DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE:-config.settings.production}

# ----------------------------------------
# Execution
# ----------------------------------------

exec python manage.py "$@"
