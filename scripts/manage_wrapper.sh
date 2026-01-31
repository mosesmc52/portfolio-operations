#!/usr/bin/env bash
set -euo pipefail

# ----------------------------------------
# Environment bootstrap
# ----------------------------------------

APP_ROOT="/app"
cd "$APP_ROOT"

# Ensure project root is importable
export PYTHONPATH="${APP_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1

# (Optional) Import container env from PID 1.
# Useful if someone runs this wrapper from a minimal env context.
# You can disable by setting WRAPPER_IMPORT_PID1_ENV=0.
if [[ "${WRAPPER_IMPORT_PID1_ENV:-1}" == "1" && -r /proc/1/environ ]]; then
  while IFS= read -r -d '' kv; do
    export "$kv" || true
  done < /proc/1/environ
fi

# Load runtime env explicitly if present.
# NOTE: this can override container env vars. If you want the opposite behavior,
# set WRAPPER_SOURCE_ENV_RUNTIME=0.
if [[ "${WRAPPER_SOURCE_ENV_RUNTIME:-1}" == "1" && -f "$APP_ROOT/.env.runtime" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$APP_ROOT/.env.runtime"
  set +a
fi

# Sensible defaults
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-core.settings}"
export DJANGO_CONFIGURATION="${DJANGO_CONFIGURATION:-Common}"

# Optional: sqlite concurrency tolerance (seconds)
export SQLITE_BUSY_TIMEOUT="${SQLITE_BUSY_TIMEOUT:-30}"

# ----------------------------------------
# Helpers
# ----------------------------------------

_resolve_sqlite_path_from_database_url() {
  local url="${DATABASE_URL:-}"
  if [[ -z "$url" ]]; then
    echo ""
    return 0
  fi
  if [[ "$url" != sqlite:* ]]; then
    echo ""
    return 0
  fi

  # Strip scheme: sqlite:
  local path="${url#sqlite:}"

  # Convert:
  #   sqlite:////data/operations.db -> /data/operations.db
  #   sqlite://///abs/path.db       -> /abs/path.db
  #   sqlite:///rel/path.db         -> rel/path.db
  if [[ "$path" == "////"* ]]; then
    echo "/${path#////}"
  elif [[ "$path" == "///"* ]]; then
    echo "${path#///}"
  else
    echo "$path"
  fi
}

# ----------------------------------------
# Quick sanity checks (fail loud)
# ----------------------------------------

if [[ ! -f "$APP_ROOT/manage.py" ]]; then
  echo "[wrapper][FATAL] manage.py not found at $APP_ROOT/manage.py (pwd=$(pwd))" >&2
  ls -la "$APP_ROOT" >&2 || true
  exit 2
fi

# Determine DB path to validate
DB_PATH="${DJANGO_DB_PATH:-}"
if [[ -z "${DB_PATH}" ]]; then
  # Prefer DATABASE_URL sqlite path if available
  DB_PATH="$(_resolve_sqlite_path_from_database_url)"
fi
# Final fallback (matches your deployment convention)
DB_PATH="${DB_PATH:-/data/operations.db}"

# If sqlite file exists but is empty, fail fast (prevents silent truncation issues)
if [[ -e "$DB_PATH" && ! -s "$DB_PATH" ]]; then
  echo "[wrapper][FATAL] SQLite DB exists but is 0 bytes: $DB_PATH" >&2
  ls -la "$(dirname "$DB_PATH")" >&2 || true
  exit 3
fi

# Optional strict mode: require DATABASE_URL for all invocations
# Enable with WRAPPER_REQUIRE_DATABASE_URL=1
if [[ "${WRAPPER_REQUIRE_DATABASE_URL:-0}" == "1" && -z "${DATABASE_URL:-}" ]]; then
  echo "[wrapper][FATAL] DATABASE_URL is required but missing" >&2
  exit 4
fi

# ----------------------------------------
# Execution
# ----------------------------------------

exec python manage.py "$@"
