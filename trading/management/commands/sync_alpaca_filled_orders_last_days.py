from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager

from django.core.management.base import BaseCommand, CommandError
from trading.sync import sync_alpaca_filled_orders_last_days


@contextmanager
def singleton_lock(lock_path: str):
    """
    Cross-process, OS-level lock to prevent multiple concurrent runs that can lock SQLite.
    macOS/Linux only (fcntl). If lock can't be acquired, raise RuntimeError.
    """
    # Ensure directory exists (e.g., /tmp always exists, but be defensive)
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)

    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        import fcntl  # macOS/Linux

        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(
                f"Another instance is already running (lock: {lock_path})"
            )
        yield
    finally:
        try:
            os.close(fd)
        except Exception:
            pass


class Command(BaseCommand):
    help = "Sync Alpaca filled orders from the last X days into TradeFill (one row per filled order)."

    def add_arguments(self, parser):
        parser.add_argument("--fund-id", type=int, required=True)
        parser.add_argument("--days", type=int, default=7)
        parser.add_argument("--limit", type=int, default=500)

        # New: prevents accidental duplicate runs
        parser.add_argument(
            "--lock-path",
            type=str,
            default="/tmp/portfolio-operations-sync-alpaca-fills.lock",
            help="Path to a file used to enforce single-instance execution.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Bypass the single-instance lock (not recommended with SQLite).",
        )

    def handle(self, *args, **opts):
        fund_id = int(opts["fund_id"])
        days = int(opts["days"])
        limit = int(opts["limit"])
        lock_path = str(opts["lock_path"])
        force = bool(opts["force"])

        def _run_sync():
            return sync_alpaca_filled_orders_last_days(
                fund_id=fund_id, days=days, limit=limit
            )

        try:
            if force:
                res = _run_sync()
            else:
                with singleton_lock(lock_path):
                    res = _run_sync()
        except Exception as e:
            # Make the error actionable for "already running" case
            msg = str(e)
            if "Another instance is already running" in msg:
                raise CommandError(
                    msg
                    + "\nTip: if you intentionally want to run anyway, pass --force "
                    "(but SQLite may lock)."
                )
            raise CommandError(msg)

        payload = {
            "fund_id": res.fund_id,
            "strategy_code": res.fund_strategy_code,
            "days": res.days,
            "limit": limit,
            "fetched": res.fetched,
            "created": res.created,
            "updated": res.updated,
        }
        self.stdout.write(json.dumps(payload, indent=2))
