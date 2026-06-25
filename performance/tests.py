from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from accounts.models import AccountBrokerCredential, ClientCapitalAccount
from clients.models import Client
from django.test import TestCase, override_settings
from funds.models import Fund
from performance.services.nav import compute_and_save_navsnapshot


@dataclass
class _FakeBrokerValuation:
    equity: Decimal
    cash: Decimal


class _FakeValuationService:
    def __init__(self, key_id: str, secret_key: str, base_url: str):
        self.key_id = key_id
        self.secret_key = secret_key
        self.base_url = base_url

    def get_account_valuation(self):
        by_key = {
            "KEY11111": _FakeBrokerValuation(
                equity=Decimal("1000.00"),
                cash=Decimal("100.00"),
            ),
            "KEY22222": _FakeBrokerValuation(
                equity=Decimal("3000.00"),
                cash=Decimal("250.00"),
            ),
        }
        return by_key[self.key_id]


@override_settings(ACCOUNT_CREDENTIALS_ENCRYPTION_KEY="test-account-credentials-key")
class NavAggregationTests(TestCase):
    def setUp(self):
        self.fund = Fund.objects.create(
            name="Alpaca Fund",
            strategy_code="ALPACA_FUND",
            inception_date=date(2026, 1, 1),
            custodian=Fund.CUSTODIAN_ALPACA,
            custodian_account_id="fund-acct",
        )

        client_one = Client.objects.create(full_name="Client One", status=Client.ACTIVE)
        client_two = Client.objects.create(full_name="Client Two", status=Client.ACTIVE)

        account_one = ClientCapitalAccount.objects.create(
            client=client_one,
            fund=self.fund,
            units="10.0",
            nav_per_unit="1.25",
            last_valuation_date=date(2026, 1, 31),
        )
        account_two = ClientCapitalAccount.objects.create(
            client=client_two,
            fund=self.fund,
            units="30.0",
            nav_per_unit="1.25",
            last_valuation_date=date(2026, 1, 31),
        )

        credential_one = AccountBrokerCredential(
            account=account_one,
            broker=Fund.CUSTODIAN_ALPACA,
        )
        credential_one.set_alpaca_credentials(key_id="KEY11111", secret_key="secret-one")
        credential_one.full_clean()
        credential_one.save()

        credential_two = AccountBrokerCredential(
            account=account_two,
            broker=Fund.CUSTODIAN_ALPACA,
            environment=AccountBrokerCredential.ENVIRONMENT_LIVE,
        )
        credential_two.set_alpaca_credentials(key_id="KEY22222", secret_key="secret-two")
        credential_two.full_clean()
        credential_two.save()

    @patch("performance.services.nav.AlpacaValuationService", _FakeValuationService)
    def test_compute_navsnapshot_aggregates_all_active_account_credentials(self):
        snap = compute_and_save_navsnapshot(fund_id=self.fund.id, as_of=date(2026, 6, 25))

        self.assertEqual(snap.aum, Decimal("4000.00"))
        self.assertEqual(snap.cash_balance, Decimal("350.00"))
        self.assertEqual(snap.total_units, Decimal("40"))
        self.assertEqual(snap.nav_per_unit, Decimal("100.00000000"))
