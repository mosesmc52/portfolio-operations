from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
import traceback
from typing import Any, Dict

from django.conf import settings
from django.core.cache import caches
from django.core.management.base import BaseCommand
from django.db import connections
from django.db.migrations.executor import MigrationExecutor
from django.db.utils import OperationalError
from django.utils import timezone


class Command(BaseCommand):
    help = "Application health check (DB, migrations, cache, clock)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-db",
            action="store_true",
            help="Skip database connectivity check",
        )
        parser.add_argument(
            "--no-migrations",
            action="store_true",
            help="Skip pending migrations check",
        )
        parser.add_argument(
            "--cache",
            action="store_true",
            help="Include cache read/write test",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Output JSON only (no human text)",
        )
        parser.add_argument(
            "--timeout-ms",
            type=int,
            default=2000,
            help="Soft timeout per check (milliseconds)",
        )

    # ---------------------------------------------------------
    # Entry point
    # ---------------------------------------------------------
    def handle(self, *args, **opts):
        start = time.monotonic()

        report: Dict[str, Any] = {
            "status": "ok",
            "checks": {},
            "meta": {
                "service": getattr(settings, "SERVICE_NAME", "django"),
                "environment": getattr(settings, "ENV", "unknown"),
                "ts_utc": timezone.now().isoformat(),
            },
        }

        failures = 0

        def run_check(name, fn):
            nonlocal failures
            try:
                t0 = time.monotonic()
                result = fn()
                elapsed = round((time.monotonic() - t0) * 1000, 2)

                report["checks"][name] = {
                    "status": "ok",
                    "ms": elapsed,
                    **(result or {}),
                }
            except Exception as e:
                failures += 1
                report["checks"][name] = {
                    "status": "fail",
                    "error": str(e),
                }

        # -----------------------------------------------------
        # Checks
        # -----------------------------------------------------
        run_check("django", self._check_django)

        if not opts["no_db"]:
            run_check("database", self._check_database)

        if not opts["no_migrations"]:
            run_check("migrations", self._check_migrations)

        if opts["cache"]:
            run_check("cache", self._check_cache)

        run_check("clock", self._check_clock)

        # -----------------------------------------------------
        # Finalize
        # -----------------------------------------------------
        total_ms = round((time.monotonic() - start) * 1000, 2)
        report["meta"]["total_ms"] = total_ms

        if failures > 0:
            report["status"] = "fail"

        # Output
        if opts["json"]:
            self.stdout.write(json.dumps(report, indent=2))
        else:
            self._print_human(report)

        # Exit code
        sys.exit(1 if failures > 0 else 0)

    # ---------------------------------------------------------
    # Individual checks
    # ---------------------------------------------------------
    def _check_django(self):
        return {
            "debug": settings.DEBUG,
            "timezone": settings.TIME_ZONE,
        }

    def _check_database(self):
        info = {}

        try:
            db_settings = settings.DATABASES["default"]
            db_path = db_settings.get("NAME")

            info["engine"] = db_settings.get("ENGINE")
            info["path"] = db_path
            info["cwd"] = os.getcwd()

            # --------------------------
            # File checks (SQLite only)
            # --------------------------
            if db_path and isinstance(db_path, str) and db_path.startswith("/"):
                info["exists"] = os.path.exists(db_path)
                if info["exists"]:
                    st = os.stat(db_path)
                    info["size_bytes"] = st.st_size
                    info["mode"] = oct(st.st_mode)
                    info["uid"] = st.st_uid
                    info["gid"] = st.st_gid
                else:
                    return {"error": f"DB file does not exist: {db_path}", **info}

            # --------------------------
            # Retry open (handles locks)
            # --------------------------
            last_err = None
            for _ in range(3):
                try:
                    db = connections["default"]
                    with db.cursor() as cursor:
                        cursor.execute("SELECT 1;")
                        row = cursor.fetchone()
                    info["ping"] = row[0]
                    return info

                except Exception as e:
                    last_err = e
                    time.sleep(1)

            raise last_err

        except Exception as e:
            return {
                "error": str(e),
                "trace": traceback.format_exc(limit=3),
                **info,
            }

    def _check_migrations(self):
        info = {}
        alias = "default"

        # Basic context
        db_settings = settings.DATABASES[alias]
        info["engine"] = db_settings.get("ENGINE")
        info["name"] = db_settings.get("NAME")
        info["cwd"] = os.getcwd()

        # File-level checks for SQLite (helpful even on Ubuntu)
        name = info["name"]
        if isinstance(name, str) and name.startswith("/"):
            info["exists"] = os.path.exists(name)
            if info["exists"]:
                st = os.stat(name)
                info["size_bytes"] = st.st_size
                info["mode"] = oct(st.st_mode)
                info["uid"] = st.st_uid
                info["gid"] = st.st_gid

        def _sqlite_pragmas(cursor):
            # Safe even if not sqlite; will just fail and we’ll ignore
            out = {}
            for q, k in [
                ("PRAGMA journal_mode;", "journal_mode"),
                ("PRAGMA locking_mode;", "locking_mode"),
                ("PRAGMA busy_timeout;", "busy_timeout"),
            ]:
                try:
                    cursor.execute(q)
                    out[k] = cursor.fetchone()
                except Exception:
                    pass
            return out

        last_err = None

        # Retry because cron can collide with other sqlite users briefly
        for attempt in range(1, 4):
            try:
                conn = connections[alias]

                # Force a fresh connection attempt (important!)
                conn.close()
                conn.connect()

                with conn.cursor() as cursor:
                    # 1) Prove we can query
                    cursor.execute("SELECT 1;")
                    info["ping"] = cursor.fetchone()[0]

                    # 2) If sqlite, capture pragmas
                    info["pragmas"] = _sqlite_pragmas(cursor)

                    # 3) Check if django_migrations table exists
                    vendor = getattr(conn, "vendor", "")
                    info["vendor"] = vendor

                    if vendor == "sqlite":
                        cursor.execute(
                            "SELECT name FROM sqlite_master WHERE type='table' AND name='django_migrations';"
                        )
                        info["django_migrations_table"] = bool(cursor.fetchone())
                    else:
                        # Generic check for other DBs
                        cursor.execute(
                            "SELECT 1 FROM information_schema.tables WHERE table_name = 'django_migrations' LIMIT 1;"
                        )
                        info["django_migrations_table"] = True

                    # If table missing, this is a schema/init problem (not “unapplied migrations”)
                    if not info.get("django_migrations_table", False):
                        raise RuntimeError(
                            f"django_migrations table missing (DB reachable). db_name={info['name']}"
                        )

                # 4) Now run the real migration plan logic
                executor = MigrationExecutor(conn)
                targets = executor.loader.graph.leaf_nodes()
                plan = executor.migration_plan(targets)

                if plan:
                    # Include first few migration IDs to make it actionable
                    sample = [f"{m.app_label}.{m.name}" for m, _ in plan[:10]]
                    raise RuntimeError(
                        f"{len(plan)} unapplied migrations; first={sample}"
                    )

                info["migrations_ok"] = True
                info["attempts"] = attempt
                return info

            except OperationalError as e:
                last_err = e
                info["attempts"] = attempt
                info["error_type"] = "OperationalError"
                info["error"] = str(e)
                info["trace"] = traceback.format_exc(limit=2)
                time.sleep(1)

            except Exception as e:
                # Non-OperationalError issues: schema missing, unapplied migrations, etc.
                last_err = e
                info["attempts"] = attempt
                info["error_type"] = type(e).__name__
                info["error"] = str(e)
                info["trace"] = traceback.format_exc(limit=2)
                break

        # If we got here, fail with detail
        raise RuntimeError(f"migrations check failed: {info}")

    def _check_cache(self):
        cache = caches["default"]
        key = "healthcheck_ping"
        cache.set(key, "ok", timeout=5)
        val = cache.get(key)

        if val != "ok":
            raise RuntimeError("cache read/write failed")

        return {"backend": cache.__class__.__name__}

    def _check_clock(self):
        now = timezone.now()
        delta = abs((timezone.now() - now).total_seconds())
        if delta > 1:
            raise RuntimeError("clock drift detected")
        return {}

    # ---------------------------------------------------------
    # Output helpers
    # ---------------------------------------------------------
    def _print_human(self, report: Dict[str, Any]):
        self.stdout.write(f"Status: {report['status'].upper()}")
        for name, check in report["checks"].items():
            if check["status"] == "ok":
                self.stdout.write(f"  ✓ {name}")
            else:
                self.stdout.write(f"  ✗ {name}: {check.get('error')}")
        self.stdout.write(f"Total: {report['meta']['total_ms']} ms")
