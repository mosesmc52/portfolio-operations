#!/usr/bin/env bash
set -euo pipefail

echo "[cron] $(date) whoami=$(whoami) pwd=$(pwd)"

export DJANGO_SETTINGS_MODULE=core.settings

python - <<'PY'
import os
from django.conf import settings

try:
    import django
    django.setup()
    print("DB_NAME:", settings.DATABASES["default"].get("NAME"))
except Exception as e:
    print("DJANGO_SETUP_ERROR:", repr(e))
PY

ls -la /data || true
ls -la /data/operations.db || true
stat /data/operations.db 2>/dev/null || true

flock -w 10 /tmp/operations_db.lock \
  /app/scripts/manage_wrapper.sh healthcheck
