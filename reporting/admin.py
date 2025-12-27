# apps/reporting/admin.py
# reporting/admin.py
from __future__ import annotations

from django.contrib import admin
from django.utils.html import format_html, mark_safe
from reporting.models import MonthlyReportArtifact


@admin.register(MonthlyReportArtifact)
class MonthlyReportArtifactAdmin(admin.ModelAdmin):
    list_display = ("snapshot", "fund", "as_of_month", "files", "created_at")
    list_filter = ("snapshot__fund", "snapshot__as_of_month")
    search_fields = ("snapshot__fund__strategy_code",)
    readonly_fields = ("files", "created_at", "updated_at")

    def fund(self, obj):
        return obj.snapshot.fund

    def as_of_month(self, obj):
        return obj.snapshot.as_of_month

    def files(self, obj):
        links = []
        if obj.html_file:
            links.append(
                format_html('<a href="{}" target="_blank">HTML</a>', obj.html_file.url)
            )
        if obj.pdf_file:
            links.append(
                format_html('<a href="{}" target="_blank">PDF</a>', obj.pdf_file.url)
            )
        if obj.chart_file:
            links.append(
                format_html(
                    '<a href="{}" target="_blank">Chart</a>', obj.chart_file.url
                )
            )
        return mark_safe(" | ".join(links))

    files.short_description = "Files"
