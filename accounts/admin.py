# accounts/admin.py
from django.contrib import admin

from .models import Account, CashFlow


class CashFlowInline(admin.TabularInline):
    model = CashFlow
    extra = 0
    fields = ("flow_date", "flow_type", "amount", "notes", "external_ref", "created_at")
    readonly_fields = ("created_at",)
    ordering = ("-flow_date",)


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = (
        "client",
        "custodian",
        "custodian_account_masked",
        "strategy_code",
        "base_currency",
        "opened_at",
        "status",
    )
    list_filter = ("custodian", "status", "base_currency", "strategy_code")
    search_fields = ("client__full_name", "custodian_account_masked", "strategy_code")
    ordering = ("-opened_at",)
    inlines = (CashFlowInline,)


@admin.register(CashFlow)
class CashFlowAdmin(admin.ModelAdmin):
    list_display = (
        "account",
        "flow_date",
        "flow_type",
        "amount",
        "external_ref",
        "created_at",
    )
    list_filter = ("flow_type", "flow_date")
    search_fields = (
        "account__client__full_name",
        "account__custodian_account_masked",
        "external_ref",
    )
    ordering = ("-flow_date", "-created_at")
    readonly_fields = ("created_at",)
