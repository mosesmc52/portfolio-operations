# apps/funds/admin.py
from django.contrib import admin

from .models import Fund


@admin.register(Fund)
class FundAdmin(admin.ModelAdmin):
    list_display = (
        "strategy_code",
        "name",
        "status",
        "custodian",
        "custodian_account_masked",
        "inception_date",
        "base_currency",
    )
    list_filter = ("status", "custodian", "base_currency")
    search_fields = (
        "strategy_code",
        "name",
        "custodian_account_id",
        "custodian_account_masked",
    )
    readonly_fields = ("created_at",)

    fieldsets = (
        ("Identity", {"fields": ("name", "strategy_code", "status", "inception_date")}),
        (
            "Custodian",
            {
                "fields": (
                    "custodian",
                    "custodian_account_id",
                    "custodian_account_masked",
                )
            },
        ),
        ("Meta", {"fields": ("base_currency", "created_at")}),
    )
