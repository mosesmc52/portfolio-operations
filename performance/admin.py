# performance/admin.py
from django.contrib import admin

from .models import MonthlySnapshot


@admin.register(MonthlySnapshot)
class MonthlySnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "account",
        "as_of_month",
        "market_value",
        "mtd_return",
        "ytd_return",
        "max_drawdown",
        "volatility",
        "strategy_version",
        "created_at",
    )
    list_filter = ("as_of_month", "strategy_version", "account__custodian")
    search_fields = ("account__client__full_name", "account__custodian_account_masked")
    ordering = ("-as_of_month", "-created_at")
    readonly_fields = ("created_at",)
    date_hierarchy = "as_of_month"
