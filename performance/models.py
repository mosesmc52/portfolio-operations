# performance/models.py
from accounts.models import Account
from django.db import models
from django.utils import timezone


class MonthlySnapshot(models.Model):
    account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="snapshots"
    )

    as_of_month = models.DateField(help_text="Use the last calendar day of the month")

    market_value = models.DecimalField(max_digits=16, decimal_places=2)

    mtd_return = models.DecimalField(
        max_digits=8, decimal_places=4, help_text="Decimal return (e.g., 0.0123)"
    )
    ytd_return = models.DecimalField(max_digits=8, decimal_places=4)

    max_drawdown = models.DecimalField(
        max_digits=8, decimal_places=4, help_text="Max drawdown since inception"
    )

    volatility = models.DecimalField(
        max_digits=8, decimal_places=4, help_text="Annualized volatility"
    )

    strategy_version = models.CharField(max_length=64, default="v1.0")

    metrics_json = models.JSONField(
        blank=True, null=True, help_text="Frozen metrics used for tear sheet"
    )

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = [("account", "as_of_month")]
        indexes = [
            models.Index(fields=["account", "as_of_month"]),
        ]

    def __str__(self):
        return f"{self.account} | {self.as_of_month}"
