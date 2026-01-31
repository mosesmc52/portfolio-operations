FROM python:3.12-slim AS backend

# -------------------------------------------------
# Runtime environment
# -------------------------------------------------
ENV PYTHONUNBUFFERED=1
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONFAULTHANDLER=1

# -------------------------------------------------
# System dependencies
# -------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    cron \
    supervisor \
    bash \
    procps \
 && rm -rf /var/lib/apt/lists/*

# -------------------------------------------------
# App setup
# -------------------------------------------------
WORKDIR /app

COPY poetry.lock pyproject.toml /app/

RUN pip install --no-cache-dir poetry \
 && poetry config virtualenvs.create false \
 && poetry install --no-root --no-interaction --no-ansi

# -------------------------------------------------
# Copy application code
# -------------------------------------------------
COPY . /app

# -------------------------------------------------
# Script entrypoints (wrapper + cron scripts)
# -------------------------------------------------
COPY scripts/manage_wrapper.sh /app/scripts/manage_wrapper.sh
COPY scripts/cron_healthcheck.sh /app/scripts/cron_healthcheck.sh
COPY scripts/cron_backup.sh /app/scripts/cron_backup.sh
COPY scripts/cron_monthly_reporting.sh /app/scripts/cron_monthly_reporting.sh
COPY scripts/cron_sync_alpaca_fills.sh /app/scripts/cron_sync_alpaca_fills.sh

RUN chmod +x \
    /app/scripts/manage_wrapper.sh \
    /app/scripts/cron_healthcheck.sh \
    /app/scripts/cron_backup.sh \
    /app/scripts/cron_monthly_reporting.sh \
    /app/scripts/cron_sync_alpaca_fills.sh

# -------------------------------------------------
# Cron + Supervisor configuration
# -------------------------------------------------
COPY docker/cron /etc/cron.d
COPY docker/supervisor/supervisord.conf /etc/supervisor/supervisord.conf

# Debian cron requires 0644 and newline endings
RUN set -euo pipefail; \
    chmod 0644 /etc/cron.d/*; \
    sed -i 's/\r$//' /etc/cron.d/*; \
    for f in /etc/cron.d/*; do \
      [ -f "$f" ] || continue; \
      tail -c 1 "$f" | read -r _ || echo >> "$f"; \
    done

# -------------------------------------------------
# Default command (scheduler container)
# -------------------------------------------------
CMD ["supervisord", "-c", "/etc/supervisor/supervisord.conf"]
