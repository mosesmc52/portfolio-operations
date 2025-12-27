# apps/performance/admin.py
from __future__ import annotations

from django.contrib import admin
from django.utils.html import format_html
from performance.models import MonthlySnapshot
from reporting.models import MonthlyReportArtifact

from .models import NAVSnapshot


@admin.register(NAVSnapshot)
class NAVSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "fund",
        "fund_strategy",
        "nav_per_unit",
        "aum",
        "total_units",
    )
    list_filter = ("fund",)
    date_hierarchy = "date"
    search_fields = ("fund__strategy_code", "fund__name")

    def fund_strategy(self, obj):
        return getattr(obj.fund, "strategy_code", "")

    fund_strategy.short_description = "Strategy"


class MonthlyReportArtifactInline(admin.StackedInline):
    """
    Inline view of the 1:1 artifact, shown on the snapshot detail page.
    """

    model = MonthlyReportArtifact  # set in get_inline_instances
    extra = 0
    can_delete = False
    readonly_fields = ("files", "created_at", "updated_at")
    fields = (
        "commentary",
        "html_file",
        "pdf_file",
        "chart_file",
        "files",
        "created_at",
        "updated_at",
    )

    def files(self, obj):
        if not obj:
            return "—"
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
        return format_html(" | ".join(links)) if links else "—"

    files.short_description = "Files"


@admin.register(MonthlySnapshot)
class MonthlySnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "fund",
        "as_of_month",
        "fund_return",
        "benchmark_symbol",
        "benchmark_return",
        "excess_return",
        "aum_eom",
        "strategy_version",
        "model_change",
        "has_report",
        "created_at",
    )
    list_filter = ("fund", "benchmark_symbol", "model_change", "as_of_month")
    search_fields = ("fund__strategy_code", "strategy_version")
    ordering = ("-as_of_month", "-created_at")

    readonly_fields = ("created_at",)

    fieldsets = (
        ("Identity", {"fields": ("fund", "as_of_month")}),
        ("NAV / AUM", {"fields": ("nav_bom", "nav_eom", "aum_eom")}),
        (
            "Performance",
            {
                "fields": (
                    "fund_return",
                    "benchmark_symbol",
                    "benchmark_return",
                    "excess_return",
                )
            },
        ),
        ("Strategy Tracking", {"fields": ("strategy_version", "model_change")}),
        ("Metrics", {"fields": ("metrics_json",)}),
        ("Timestamps", {"fields": ("created_at",)}),
    )

    def get_inline_instances(self, request, obj=None):
        # Avoid circular imports at module import time
        from reporting.models import MonthlyReportArtifact

        MonthlyReportArtifactInline.model = MonthlyReportArtifact
        return super().get_inline_instances(request, obj=obj)

    inlines = [MonthlyReportArtifactInline]

    def has_report(self, obj: MonthlySnapshot):
        return hasattr(obj, "report_artifact") and obj.report_artifact is not None

    has_report.boolean = True
    has_report.short_description = "Report?"
