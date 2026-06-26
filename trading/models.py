from django.db import models

# Create your models here.


class TradeFill(models.Model):
    fund = models.ForeignKey("funds.Fund", on_delete=models.CASCADE)
    account = models.ForeignKey(
        "accounts.ClientCapitalAccount",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    broker = models.CharField(max_length=16)  # ALPACA
    external_fill_id = models.CharField(max_length=128)

    symbol = models.CharField(max_length=32)
    side = models.CharField(max_length=8)  # buy/sell
    qty = models.DecimalField(max_digits=18, decimal_places=6)
    price = models.DecimalField(max_digits=18, decimal_places=6)
    notional = models.DecimalField(max_digits=20, decimal_places=2)

    filled_at = models.DateTimeField()

    raw = models.JSONField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["account", "external_fill_id"],
                name="uq_tradefill_account_external_fill_id",
            )
        ]
