from django.db import models


class FundExpense(models.Model):
    TYPE_MGMT_FEE = "MGMT_FEE"
    TYPE_CHOICES = [
        (TYPE_MGMT_FEE, "Management Fee"),
    ]

    fund = models.ForeignKey("funds.Fund", on_delete=models.PROTECT)
    expense_type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    as_of_date = models.DateField()

    # Accrued or crystallized amount (USD)
    amount = models.DecimalField(max_digits=18, decimal_places=2)

    # Optional: link to payout transfer reference / note
    external_ref = models.CharField(max_length=128, blank=True, null=True)

    # Whether this expense has been paid out of broker cash yet
    is_paid = models.BooleanField(default=False)
    paid_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["fund", "expense_type", "as_of_date"],
                name="uq_fundexpense_fund_type_date",
            )
        ]

    def __str__(self):
        return f"{self.fund.strategy_code} {self.expense_type} {self.as_of_date} ${self.amount}"
