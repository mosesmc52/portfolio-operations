# apps/performance/admin.py
from django.contrib import admin

from .models import MonthlySnapshot, NAVSnapshot


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


@admin.register(MonthlySnapshot)
class MonthlySnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "as_of_month",
        "fund",
        "fund_strategy",
        "nav_eom",
        "aum_eom",
        "benchmark_symbol",
        "fund_return",
        "benchmark_return",
        "excess_return",
        "strategy_version",
        "model_change",
    )
    list_filter = ("fund", "benchmark_symbol", "model_change", "strategy_version")
    date_hierarchy = "as_of_month"
    search_fields = ("fund__strategy_code", "fund__name", "strategy_version")
    readonly_fields = ("created_at",)

    fieldsets = (
        ("Period", {"fields": ("fund", "as_of_month")}),
        ("NAV", {"fields": ("nav_bom", "nav_eom", "aum_eom")}),
        (
            "Benchmark",
            {
                "fields": (
                    "benchmark_symbol",
                    "benchmark_return",
                    "fund_return",
                    "excess_return",
                )
            },
        ),
        ("Model", {"fields": ("strategy_version", "model_change")}),
        ("Metrics JSON", {"fields": ("metrics_json",)}),
        ("Meta", {"fields": ("created_at",)}),
    )

    def fund_strategy(self, obj):
        return getattr(obj.fund, "strategy_code", "")

    fund_strategy.short_description = "Strategy"
