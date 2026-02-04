from __future__ import annotations

from celery import shared_task
from django.db import transaction
from operations.models import BackupRun
from operations.services.backups import backup_sqlite_db_to_spaces


@shared_task(bind=True)
def backup_operations_db_to_spaces_task(
    self,
    *,
    db_path: str = "/data/operations.db",
    prefix: str = "backups/operations",
    filename: str = "operations",
    max_days: int = 30,
    gzip_enabled: bool = True,
    acl: str = "private",
    dry_run: bool = False,
) -> dict:
    # Create history row first (so failures are captured)
    with transaction.atomic():
        run = BackupRun.objects.create(
            status=BackupRun.Status.STARTED,
            target="operations_db",
            db_path=db_path,
            prefix=prefix,
            filename=filename,
            max_days=max_days,
            gzip_enabled=gzip_enabled,
            acl=acl,
            dry_run=dry_run,
            task_id=(self.request.id or ""),
        )

    try:
        res = backup_sqlite_db_to_spaces(
            db_path=db_path,
            target="operations_db",
            prefix=prefix,
            filename=filename,
            max_days=max_days,
            gzip_enabled=gzip_enabled,
            acl=acl,
            dry_run=dry_run,
            backup_run=run,  # function will mark success
        )
    except Exception as e:
        run.mark_failed(error=str(e))
        raise

    return {
        "ok": True,
        "backup_run_id": run.id,
        "task_id": self.request.id,
        "db_path": res.db_path,
        "bucket": res.bucket,
        "region": res.region,
        "endpoint": res.endpoint,
        "key": res.key,
        "uploaded_bytes": res.uploaded_bytes,
        "compressed": res.compressed,
        "max_days": res.max_days,
        "deleted_old": res.deleted_old,
        "kept": res.kept,
        "dry_run": dry_run,
    }
