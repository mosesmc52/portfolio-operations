# apps/trading/admin.py
from django.contrib import admin
from django.db.models import Sum
from django.utils.timezone import localtime

from .models import TradeFill


@admin.register(TradeFill)
class TradeFillAdmin(admin.ModelAdmin):
    list_display = (
        "filled_at_local",
        "fund",
        "account",
        "fund_strategy",
        "symbol",
        "side",
        "qty",
        "price",
        "notional",
        "broker",
        "external_fill_id",
    )
    list_filter = ("broker", "side", "symbol", "fund", "account")
    search_fields = (
        "external_fill_id",
        "symbol",
        "account__client__full_name",
        "fund__strategy_code",
        "fund__name",
    )
    date_hierarchy = "filled_at"
    readonly_fields = ("created_at",)

    def filled_at_local(self, obj):
        return localtime(obj.filled_at).strftime("%Y-%m-%d %H:%M")

    filled_at_local.short_description = "Filled (local)"

    def fund_strategy(self, obj):
        return getattr(obj.fund, "strategy_code", "")

    fund_strategy.short_description = "Strategy"

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        qs = self.get_queryset(request)
        extra_context["total_notional"] = qs.aggregate(Sum("notional"))["notional__sum"]
        return super().changelist_view(request, extra_context=extra_context)
