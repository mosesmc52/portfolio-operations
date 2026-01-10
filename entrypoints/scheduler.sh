#!/usr/bin/env bash
set -euo pipefail

# Ensure migrations are handled elsewhere (recommended), or do it here cautiously.
# python manage.py migrate --noinput

exec supervisord -c /etc/supervisor/supervisord.conf
