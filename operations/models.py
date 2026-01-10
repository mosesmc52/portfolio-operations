# Create your models here.
from __future__ import annotations

from django.db import models
from django.utils import timezone


class BackupRun(models.Model):
    class Status(models.TextChoices):
        STARTED = "STARTED", "Started"
        SUCCESS = "SUCCESS", "Success"
        FAILED = "FAILED", "Failed"

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True, db_index=True)

    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.STARTED, db_index=True
    )

    # What was backed up
    target = models.CharField(
        max_length=64,
        default="operations_db",
        help_text="Logical backup target (e.g., operations_db).",
        db_index=True,
    )
    db_path = models.CharField(max_length=512, default="/data/operations.db")

    # Where it went in Spaces
    bucket = models.CharField(max_length=128, blank=True, default="")
    region = models.CharField(max_length=64, blank=True, default="")
    endpoint = models.CharField(max_length=256, blank=True, default="")
    key = models.CharField(max_length=512, blank=True, default="", db_index=True)

    # Parameters used
    prefix = models.CharField(max_length=256, default="backups/operations")
    filename = models.CharField(max_length=128, default="operations")
    max_days = models.PositiveIntegerField(default=30)
    gzip_enabled = models.BooleanField(default=True)
    acl = models.CharField(max_length=32, default="private")
    dry_run = models.BooleanField(default=False)

    # Outcomes
    uploaded_bytes = models.BigIntegerField(default=0)
    compressed = models.BooleanField(default=False)
    deleted_old = models.IntegerField(default=0)
    kept = models.IntegerField(default=0)

    # Diagnostics
    task_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    error = models.TextField(blank=True, default="")

    def mark_success(
        self,
        *,
        bucket: str,
        region: str,
        endpoint: str,
        key: str,
        uploaded_bytes: int,
        compressed: bool,
        deleted_old: int,
        kept: int,
    ) -> None:
        self.status = self.Status.SUCCESS
        self.finished_at = timezone.now()
        self.bucket = bucket
        self.region = region
        self.endpoint = endpoint
        self.key = key
        self.uploaded_bytes = int(uploaded_bytes or 0)
        self.compressed = bool(compressed)
        self.deleted_old = int(deleted_old or 0)
        self.kept = int(kept or 0)
        self.error = ""
        self.save(
            update_fields=[
                "status",
                "finished_at",
                "bucket",
                "region",
                "endpoint",
                "key",
                "uploaded_bytes",
                "compressed",
                "deleted_old",
                "kept",
                "error",
            ]
        )

    def mark_failed(self, *, error: str) -> None:
        self.status = self.Status.FAILED
        self.finished_at = timezone.now()
        self.error = (error or "")[:20000]
        self.save(update_fields=["status", "finished_at", "error"])

    def __str__(self) -> str:
        return f"[{self.status}] {self.target} @ {self.created_at:%Y-%m-%d %H:%M:%S}"
