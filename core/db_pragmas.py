import logging

from django.db.utils import OperationalError

log = logging.getLogger(__name__)


def enable_sqlite_pragmas(sender, connection, **kwargs):
    if connection.vendor != "sqlite":
        return

    try:
        with connection.cursor() as cursor:
            # safe + useful on every connection
            cursor.execute("PRAGMA busy_timeout=30000;")  # 30s
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute("PRAGMA foreign_keys=ON;")

            # journal_mode can fail if another process is touching the DB.
            # It's persistent (stored in the DB), so we *try* but don't die.
            cursor.execute("PRAGMA journal_mode=WAL;")

    except OperationalError as e:
        # Don't break boot; log and continue
        msg = str(e).lower()
        if "database is locked" in msg:
            log.warning("SQLite is locked while applying PRAGMAs; continuing: %s", e)
            return
        raise
