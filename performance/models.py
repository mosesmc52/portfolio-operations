# apps/performance/models.py
from django.db import models


class NAVSnapshot(models.Model):
    fund = models.ForeignKey(
        "funds.Fund",
        on_delete=models.CASCADE,
        related_name="nav_snapshots",
    )

    date = models.DateField(help_text="Valuation date")

    nav_per_unit = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        help_text="NAV per unit on this date",
    )

    total_units = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        help_text="Total outstanding units",
    )

    aum = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text="Assets under management (USD)",
    )

    cash_balance = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional: broker cash balance",
    )

    gross_exposure = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        null=True,
        blank=True,
    )

    net_exposure = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("fund", "date")]
        ordering = ["-date"]
        indexes = [
            models.Index(fields=["fund", "date"]),
        ]

    def __str__(self):
        return f"{self.fund.strategy_code} NAV {self.date}"


class MonthlySnapshot(models.Model):
    fund = models.ForeignKey(
        "funds.Fund",
        on_delete=models.CASCADE,
        related_name="monthly_snapshots",
    )

    as_of_month = models.DateField(help_text="Month end date (YYYY-MM-last_day)")

    nav_bom = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        help_text="NAV at beginning of month",
    )

    nav_eom = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        help_text="NAV at end of month",
    )

    aum_eom = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text="AUM at month end",
    )

    fund_return = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        help_text="Fund return for the month (decimal, e.g. 0.0234)",
    )

    benchmark_symbol = models.CharField(
        max_length=16,
        default="SPY",
    )

    benchmark_return = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        help_text="Benchmark return for same period",
    )

    excess_return = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        help_text="Fund - benchmark",
    )

    strategy_version = models.CharField(
        max_length=64,
        help_text="Strategy version hash or tag",
    )

    model_change = models.BooleanField(
        default=False,
        help_text="True if model/logic changed this month",
    )

    metrics_json = models.JSONField(
        default=dict,
        help_text="Drawdown, volatility, Sharpe, exposure stats, etc.",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("fund", "as_of_month")]
        ordering = ["-as_of_month"]
        indexes = [
            models.Index(fields=["fund", "as_of_month"]),
        ]

    def __str__(self):
        return f"{self.fund.strategy_code} {self.as_of_month:%Y-%m}"
