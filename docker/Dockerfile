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
# Wrapper entrypoints
# -------------------------------------------------
COPY scripts/manage_wrapper.sh /app/scripts/manage_wrapper.sh
RUN chmod +x /app/scripts/manage_wrapper.sh

# -------------------------------------------------
# Cron + Supervisor configuration
# -------------------------------------------------
COPY docker/cron /etc/cron.d
COPY docker/supervisor/supervisord.conf /etc/supervisor/supervisord.conf

RUN chmod 0644 /etc/cron.d/*


# -------------------------------------------------
# Default command (scheduler container)
# -------------------------------------------------
CMD ["supervisord", "-c", "/etc/supervisor/supervisord.conf"]
