#!/usr/bin/env bash
set -euo pipefail

cd /app

python manage.py migrate --noinput

exec python manage.py runserver 0.0.0.0:8000 --insecure
