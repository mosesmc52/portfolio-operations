from __future__ import annotations

import base64
import hashlib
from typing import Tuple

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import models
from funds.models import Fund


def _credential_fernet() -> Fernet:
    raw_key = (getattr(settings, "ACCOUNT_CREDENTIALS_ENCRYPTION_KEY", "") or "").strip()
    if not raw_key:
        raise ImproperlyConfigured(
            "ACCOUNT_CREDENTIALS_ENCRYPTION_KEY must be configured to read or write "
            "account broker credentials."
        )

    derived_key = base64.urlsafe_b64encode(hashlib.sha256(raw_key.encode("utf-8")).digest())
    return Fernet(derived_key)


class ClientCapitalAccount(models.Model):
    client = models.ForeignKey("clients.Client", on_delete=models.CASCADE)
    fund = models.ForeignKey("funds.Fund", on_delete=models.CASCADE)

    units = models.DecimalField(max_digits=20, decimal_places=8)
    nav_per_unit = models.DecimalField(max_digits=18, decimal_places=8)

    last_valuation_date = models.DateField()

    class Meta:
        unique_together = [("client", "fund")]

    def __str__(self) -> str:
        return f"{self.client} / {self.fund}"


class AccountBrokerCredential(models.Model):
    ENVIRONMENT_PAPER = "paper"
    ENVIRONMENT_LIVE = "live"
    ENVIRONMENT_CHOICES = [
        (ENVIRONMENT_PAPER, "Paper"),
        (ENVIRONMENT_LIVE, "Live"),
    ]

    account = models.OneToOneField(
        "accounts.ClientCapitalAccount",
        on_delete=models.CASCADE,
        related_name="broker_credential",
    )
    broker = models.CharField(
        max_length=16,
        choices=Fund.CUSTODIAN_CHOICES,
        default=Fund.CUSTODIAN_ALPACA,
    )
    environment = models.CharField(
        max_length=16,
        choices=ENVIRONMENT_CHOICES,
        default=ENVIRONMENT_PAPER,
    )
    alpaca_key_id_encrypted = models.TextField(blank=True, default="")
    alpaca_secret_key_encrypted = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["broker", "is_active"]),
        ]

    def clean(self) -> None:
        if self.broker != self.account.fund.custodian:
            raise ValidationError(
                {"broker": "Broker must match the associated account fund custodian."}
            )

    def set_alpaca_credentials(self, *, key_id: str, secret_key: str) -> None:
        if self.broker != Fund.CUSTODIAN_ALPACA:
            raise ValidationError("Alpaca credentials can only be stored for ALPACA broker rows.")

        if not key_id or not secret_key:
            raise ValidationError("Both Alpaca key ID and secret key are required.")

        fernet = _credential_fernet()
        self.alpaca_key_id_encrypted = fernet.encrypt(key_id.encode("utf-8")).decode("ascii")
        self.alpaca_secret_key_encrypted = fernet.encrypt(secret_key.encode("utf-8")).decode(
            "ascii"
        )

    def get_alpaca_credentials(self) -> Tuple[str, str]:
        if not self.alpaca_key_id_encrypted or not self.alpaca_secret_key_encrypted:
            raise ValidationError("Encrypted Alpaca credentials are not set.")

        fernet = _credential_fernet()
        try:
            key_id = fernet.decrypt(self.alpaca_key_id_encrypted.encode("ascii")).decode("utf-8")
            secret_key = fernet.decrypt(self.alpaca_secret_key_encrypted.encode("ascii")).decode(
                "utf-8"
            )
        except InvalidToken as exc:
            raise ValidationError("Stored Alpaca credentials could not be decrypted.") from exc

        return key_id, secret_key

    def get_alpaca_base_url(self) -> str:
        if self.environment == self.ENVIRONMENT_LIVE:
            return "https://api.alpaca.markets"
        return "https://paper-api.alpaca.markets"

    @property
    def masked_key_id(self) -> str:
        if not self.alpaca_key_id_encrypted:
            return ""
        try:
            key_id, _ = self.get_alpaca_credentials()
        except (ValidationError, ImproperlyConfigured):
            return "[unavailable]"
        if len(key_id) <= 4:
            return "*" * len(key_id)
        return f"{key_id[:4]}{'*' * max(len(key_id) - 8, 4)}{key_id[-4:]}"

    def __str__(self) -> str:
        return f"{self.account} {self.get_broker_display()} credentials"


class AccountPortfolioHistory(models.Model):
    account = models.ForeignKey(
        "accounts.ClientCapitalAccount",
        on_delete=models.CASCADE,
        related_name="portfolio_history",
    )
    broker = models.CharField(max_length=16, choices=Fund.CUSTODIAN_CHOICES)
    as_of_date = models.DateField()
    as_of_datetime = models.DateTimeField()
    timeframe = models.CharField(max_length=16, default="1D")
    equity = models.DecimalField(max_digits=20, decimal_places=2)
    profit_loss = models.DecimalField(max_digits=20, decimal_places=2)
    profit_loss_pct = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True,
    )
    base_value = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        null=True,
        blank=True,
    )
    raw = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["account", "as_of_datetime", "timeframe"],
                name="uq_acct_portfolio_history_account_dt_timeframe",
            )
        ]
        indexes = [
            models.Index(fields=["account", "as_of_date"]),
            models.Index(fields=["account", "timeframe"]),
        ]
        ordering = ["account_id", "-as_of_datetime"]

    def __str__(self) -> str:
        return f"{self.account} {self.as_of_date} {self.timeframe}"


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
