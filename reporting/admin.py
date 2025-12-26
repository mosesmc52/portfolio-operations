# apps/reporting/admin.py
from django.contrib import admin

from .models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = (
        "snapshot",
        "fund",
        "fund_strategy",
        "created_at",
        "llm_model",
        "has_commentary_pdf",
        "has_tearsheet_pdf",
    )
    list_filter = ("llm_model",)
    search_fields = (
        "snapshot__fund__strategy_code",
        "snapshot__fund__name",
        "snapshot__as_of_month",
    )
    readonly_fields = ("created_at", "prompt_hash", "inputs_hash")

    def fund(self, obj):
        return getattr(obj.snapshot, "fund", None)

    fund.short_description = "Fund"

    def fund_strategy(self, obj):
        f = getattr(obj.snapshot, "fund", None)
        return getattr(f, "strategy_code", "") if f else ""

    fund_strategy.short_description = "Strategy"

    def has_commentary_pdf(self, obj):
        return bool(getattr(obj, "commentary_pdf_path", None))

    has_commentary_pdf.boolean = True
    has_commentary_pdf.short_description = "Commentary PDF"

    def has_tearsheet_pdf(self, obj):
        return bool(getattr(obj, "tearsheet_pdf_path", None))

    has_tearsheet_pdf.boolean = True
    has_tearsheet_pdf.short_description = "Tearsheet PDF"
