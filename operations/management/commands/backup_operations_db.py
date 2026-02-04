from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError
from operations.services.backups import backup_sqlite_db_to_spaces  # update path
from operations.task import backup_operations_db_to_spaces_task  # update path


class Command(BaseCommand):
    help = "Backup the operations SQLite DB to DigitalOcean Spaces + prune old backups."

    def add_arguments(self, parser):
        parser.add_argument("--db-path", type=str, default="/data/operations.db")
        parser.add_argument("--prefix", type=str, default="backups/operations")
        parser.add_argument("--filename", type=str, default="operations")
        parser.add_argument("--max-days", type=int, default=30)

        parser.add_argument(
            "--gzip", dest="gzip_enabled", action="store_true", default=True
        )
        parser.add_argument("--no-gzip", dest="gzip_enabled", action="store_false")

        parser.add_argument(
            "--acl",
            type=str,
            default="private",
            choices=["private", "public-read"],
            help="ACL for uploaded backup object (default: private).",
        )

        parser.add_argument("--dry-run", action="store_true", default=False)
        parser.add_argument(
            "--async",
            dest="run_async",
            action="store_true",
            default=False,
            help="Queue backup as a Celery task (requires broker/worker).",
        )

        parser.add_argument("--json", action="store_true", default=False)

    def handle(self, *args, **opts):
        db_path = opts["db_path"]
        prefix = opts["prefix"]
        filename = opts["filename"]
        max_days = int(opts["max_days"])
        gzip_enabled = bool(opts["gzip_enabled"])
        acl = opts["acl"]
        dry_run = bool(opts["dry_run"])
        run_async = bool(opts["run_async"])

        try:
            if run_async:
                ar = backup_operations_db_to_spaces_task.delay(
                    db_path=db_path,
                    prefix=prefix,
                    filename=filename,
                    max_days=max_days,
                    gzip_enabled=gzip_enabled,
                    acl=acl,
                    dry_run=dry_run,
                )
                payload = {
                    "queued": True,
                    "task_id": ar.id,
                    "db_path": db_path,
                    "prefix": prefix,
                    "filename": filename,
                    "max_days": max_days,
                    "gzip_enabled": gzip_enabled,
                    "acl": acl,
                    "dry_run": dry_run,
                }
            else:
                res = backup_sqlite_db_to_spaces(
                    db_path=db_path,
                    prefix=prefix,
                    filename=filename,
                    max_days=max_days,
                    gzip_enabled=gzip_enabled,
                    acl=acl,
                    dry_run=dry_run,
                )
                payload = {
                    "queued": False,
                    "ok": res.ok,
                    "db_path": res.db_path,
                    "bucket": res.bucket,
                    "endpoint": res.endpoint,
                    "key": res.key,
                    "uploaded_bytes": res.uploaded_bytes,
                    "compressed": res.compressed,
                    "max_days": res.max_days,
                    "deleted_old": res.deleted_old,
                    "kept": res.kept,
                    "acl": acl,
                    "dry_run": dry_run,
                }

        except Exception as e:
            raise CommandError(str(e))

        if opts["json"]:
            self.stdout.write(json.dumps(payload, indent=2))
        else:
            self.stdout.write(json.dumps(payload, indent=2))
        return None
