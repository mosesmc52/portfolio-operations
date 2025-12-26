from django.db import models


class ClientCapitalAccount(models.Model):
    client = models.ForeignKey("clients.Client", on_delete=models.CASCADE)
    fund = models.ForeignKey("funds.Fund", on_delete=models.CASCADE)

    units = models.DecimalField(max_digits=20, decimal_places=8)
    nav_per_unit = models.DecimalField(max_digits=18, decimal_places=8)

    last_valuation_date = models.DateField()

    class Meta:
        unique_together = [("client", "fund")]


class CapitalFlow(models.Model):
    TYPE_SUBSCRIPTION = "SUB"
    TYPE_REDEMPTION = "RED"

    FLOW_TYPE_CHOICES = [
        (TYPE_SUBSCRIPTION, "Subscription (Deposit)"),
        (TYPE_REDEMPTION, "Redemption (Withdraw)"),
    ]

    client = models.ForeignKey("clients.Client", on_delete=models.CASCADE)
    fund = models.ForeignKey("funds.Fund", on_delete=models.CASCADE)

    flow_type = models.CharField(max_length=8, choices=FLOW_TYPE_CHOICES)

    amount = models.DecimalField(max_digits=18, decimal_places=2)
    nav_at_flow = models.DecimalField(max_digits=18, decimal_places=8)
    units_delta = models.DecimalField(max_digits=20, decimal_places=8)

    flow_date = models.DateField()
    external_ref = models.CharField(max_length=128, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["fund", "client", "external_ref"],
                name="uq_capitalflow_fund_client_external_ref",
            )
        ]

    def __str__(self):
        return f"{self.client} {self.flow_type} {self.amount} on {self.flow_date}"
