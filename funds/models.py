# apps/funds/models.py
from django.db import models


class Fund(models.Model):
    # -----------------------------
    # Custodian choices (broker-agnostic)
    # -----------------------------
    CUSTODIAN_ALPACA = "ALPACA"
    CUSTODIAN_IBKR = "IBKR"

    CUSTODIAN_CHOICES = [
        (CUSTODIAN_ALPACA, "Alpaca"),
        (CUSTODIAN_IBKR, "Interactive Brokers"),
    ]

    # -----------------------------
    # Fund lifecycle status
    # -----------------------------
    STATUS_ACTIVE = "ACTIVE"
    STATUS_PAUSED = "PAUSED"
    STATUS_CLOSED = "CLOSED"

    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_PAUSED, "Paused"),
        (STATUS_CLOSED, "Closed"),
    ]

    # -----------------------------
    # Identity
    # -----------------------------
    name = models.CharField(
        max_length=128,
        help_text="Human-readable fund name",
    )

    strategy_code = models.CharField(
        max_length=64,
        unique=True,
        help_text="Internal strategy identifier (e.g. ETF_MOM_V1)",
    )

    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
    )

    inception_date = models.DateField()

    # -----------------------------
    # Custodian / Broker
    # -----------------------------
    custodian = models.CharField(
        max_length=16,
        choices=CUSTODIAN_CHOICES,
        help_text="Trading custodian / broker",
    )

    custodian_account_id = models.CharField(
        max_length=128,
        help_text="Broker-specific account identifier",
    )

    custodian_account_masked = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text="Masked broker account (e.g. ****1234)",
    )

    base_currency = models.CharField(
        max_length=8,
        default="USD",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["strategy_code"]),
            models.Index(fields=["custodian", "status"]),
        ]

    def __str__(self):
        return f"{self.strategy_code} ({self.get_custodian_display()})"
