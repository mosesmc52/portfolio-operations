from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Configure SQLite PRAGMAs (WAL, busy_timeout, etc.)"

    def handle(self, *args, **options):
        if connection.vendor != "sqlite":
            self.stdout.write(self.style.WARNING("Not SQLite; skipping."))
            return

        with connection.cursor() as cursor:
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute("PRAGMA busy_timeout=30000;")
            cursor.execute("PRAGMA foreign_keys=ON;")

            mode = cursor.execute("PRAGMA journal_mode;").fetchone()[0]
            self.stdout.write(
                self.style.SUCCESS(f"SQLite configured. journal_mode={mode}")
            )
