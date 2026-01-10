from __future__ import annotations

from django.contrib import admin

from .models import BackupRun

# Register your models here.


@admin.register(BackupRun)
class BackupRunAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "status",
        "target",
        "uploaded_bytes",
        "compressed",
        "deleted_old",
        "kept",
        "bucket",
        "key",
        "dry_run",
    )
    list_filter = ("status", "target", "gzip_enabled", "dry_run", "acl", "max_days")
    search_fields = (
        "key",
        "bucket",
        "task_id",
        "db_path",
        "prefix",
        "filename",
        "error",
    )
    readonly_fields = (
        "created_at",
        "finished_at",
        "status",
        "target",
        "db_path",
        "bucket",
        "region",
        "endpoint",
        "key",
        "prefix",
        "filename",
        "max_days",
        "gzip_enabled",
        "acl",
        "dry_run",
        "uploaded_bytes",
        "compressed",
        "deleted_old",
        "kept",
        "task_id",
        "error",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
