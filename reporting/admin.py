# reporting/admin.py
from django.contrib import admin

from .models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = (
        "snapshot",
        "tearsheet_pdf_path",
        "commentary_md_path",
        "commentary_pdf_path",
        "llm_model",
        "created_at",
    )
    list_filter = ("llm_model", "created_at")
    search_fields = (
        "snapshot__account__client__full_name",
        "snapshot__account__custodian_account_masked",
        "snapshot__as_of_month",
    )
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)
