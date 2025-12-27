# apps/performance/admin.py
from __future__ import annotations

from django.contrib import admin, messages
from django.db.models import Sum
from django.utils import timezone
from fees.models import FundExpense


@admin.register(FundExpense)
class FundExpenseAdmin(admin.ModelAdmin):
    list_display = (
        "as_of_date",
        "fund",
        "expense_type",
        "amount",
        "is_paid",
        "paid_at",
        "external_ref",
        "created_at",
    )
    list_filter = ("fund", "expense_type", "is_paid")
    search_fields = ("fund__strategy_code", "fund__name", "external_ref")
    date_hierarchy = "as_of_date"
    ordering = ("-as_of_date", "-created_at")

    # Ledger-like fields should not be casually edited after creation
    readonly_fields = ("created_at",)

    fields = (
        "fund",
        "expense_type",
        "as_of_date",
        "amount",
        "external_ref",
        "is_paid",
        "paid_at",
        "created_at",
    )

    actions = ("mark_paid", "mark_unpaid")

    @admin.action(
        description="Mark selected expenses as PAID (sets paid_at=now if missing)"
    )
    def mark_paid(self, request, queryset):
        now = timezone.now()
        updated = 0
        for exp in queryset:
            if not exp.is_paid:
                exp.is_paid = True
                if not exp.paid_at:
                    exp.paid_at = now
                exp.save(update_fields=["is_paid", "paid_at"])
                updated += 1
        self.message_user(
            request, f"Marked {updated} expense(s) as paid.", level=messages.SUCCESS
        )

    @admin.action(description="Mark selected expenses as UNPAID (clears paid_at)")
    def mark_unpaid(self, request, queryset):
        updated = queryset.update(is_paid=False, paid_at=None)
        self.message_user(
            request, f"Marked {updated} expense(s) as unpaid.", level=messages.SUCCESS
        )

    def changelist_view(self, request, extra_context=None):
        """
        Adds a small summary of unpaid fees to the changelist page context.
        """
        extra_context = extra_context or {}
        unpaid_total = (
            FundExpense.objects.filter(is_paid=False)
            .aggregate(total=Sum("amount"))
            .get("total")
            or 0
        )
        extra_context["unpaid_total"] = unpaid_total
        return super().changelist_view(request, extra_context=extra_context)
