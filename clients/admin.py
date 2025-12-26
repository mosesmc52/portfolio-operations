# apps/clients/admin.py
from __future__ import annotations

from decimal import Decimal

from accounts.models import ClientCapitalAccount
from clients.models import Client
from django.contrib import admin
from django.db.models import (
    DecimalField,
    ExpressionWrapper,
    F,
    OuterRef,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce
from performance.models import NAVSnapshot


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "full_name",
        "client_type",
        "status",
        "market_value_usd",
        "created_at",
    )
    list_filter = ("status", "client_type")
    search_fields = ("full_name", "email")
    readonly_fields = ("created_at",)

    def get_queryset(self, request):
        """
        Annotate each Client row with total market value across all funds:
          sum(units * latest_nav_per_unit_for_fund)
        """
        qs = super().get_queryset(request)

        # Latest NAV per unit for a given fund
        latest_nav_sq = (
            NAVSnapshot.objects.filter(fund=OuterRef("fund_id"))
            .order_by("-date")
            .values("nav_per_unit")[:1]
        )

        # Per-client market value across all capital accounts
        per_client_total_sq = (
            ClientCapitalAccount.objects.filter(client=OuterRef("pk"))
            .annotate(
                latest_nav=Subquery(
                    latest_nav_sq,
                    output_field=DecimalField(max_digits=18, decimal_places=8),
                )
            )
            .annotate(
                mv=ExpressionWrapper(
                    Coalesce(F("units"), Value(Decimal("0")))
                    * Coalesce(F("latest_nav"), Value(Decimal("0"))),
                    output_field=DecimalField(max_digits=20, decimal_places=2),
                )
            )
            .values("client")
            .annotate(total_mv=Coalesce(Sum("mv"), Value(Decimal("0"))))
            .values("total_mv")[:1]
        )

        return qs.annotate(
            market_value=Coalesce(
                Subquery(
                    per_client_total_sq,
                    output_field=DecimalField(max_digits=20, decimal_places=2),
                ),
                Value(Decimal("0.00")),
            )
        )

    @admin.display(ordering="market_value", description="Market Value (USD)")
    def market_value_usd(self, obj: Client) -> str:
        mv = getattr(obj, "market_value", None) or Decimal("0.00")
        return f"${mv:,.2f}"
