# accounts/models.py
from clients.models import Client
from django.db import models
from django.utils import timezone


class Account(models.Model):
    ALPACA = "ALPACA"
    IBKR = "IBKR"
    OTHER = "OTHER"

    CUSTODIAN_CHOICES = [
        (ALPACA, "Alpaca"),
        (IBKR, "Interactive Brokers"),
        (OTHER, "Other"),
    ]

    ACTIVE = "active"
    CLOSED = "closed"
    STATUS_CHOICES = [
        (ACTIVE, "Active"),
        (CLOSED, "Closed"),
    ]

    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name="accounts"
    )

    custodian = models.CharField(
        max_length=20, choices=CUSTODIAN_CHOICES, default=ALPACA
    )
    custodian_account_masked = models.CharField(
        max_length=32,
        help_text="Masked account identifier (e.g., last 4 digits)",
    )

    base_currency = models.CharField(max_length=10, default="USD")
    strategy_code = models.CharField(max_length=64, default="ETF_WKLY_V1")

    opened_at = models.DateField(default=timezone.now)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=ACTIVE)

    class Meta:
        unique_together = [("custodian", "custodian_account_masked")]

    def __str__(self):
        return f"{self.client.full_name} | {self.custodian} {self.custodian_account_masked}"


class CashFlow(models.Model):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    FEE = "fee"

    FLOW_TYPE_CHOICES = [
        (DEPOSIT, "Deposit"),
        (WITHDRAWAL, "Withdrawal"),
        (FEE, "Fee"),
    ]

    account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="cashflows"
    )

    flow_date = models.DateField()
    flow_type = models.CharField(max_length=20, choices=FLOW_TYPE_CHOICES)

    # Always store as POSITIVE; sign is derived from flow_type
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    notes = models.CharField(max_length=255, blank=True, null=True)
    external_ref = models.CharField(max_length=128, blank=True, null=True)

    created_at = models.DateTimeField(default=timezone.now)

    def signed_amount(self):
        if self.flow_type == self.DEPOSIT:
            return self.amount
        return -self.amount

    def __str__(self):
        return f"{self.flow_type} {self.amount} on {self.flow_date}"
