from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from accounts.models import (
    AccountBrokerCredential,
    AccountPortfolioHistory,
    ClientCapitalAccount,
)
from accounts.services.portfolio_history import sync_alpaca_account_portfolio_history
from clients.models import Client
from django.test import TestCase, override_settings
from funds.models import Fund


@dataclass
class _FakeHistoryPoint:
    as_of_datetime: datetime
    equity: Decimal
    profit_loss: Decimal
    profit_loss_pct: Decimal | None
    base_value: Decimal | None
    timeframe: str
    raw: dict


class _FakePortfolioHistoryService:
    def __init__(self, key_id: str, secret_key: str, base_url: str):
        self.key_id = key_id
        self.secret_key = secret_key
        self.base_url = base_url

    def get_daily_portfolio_history(self, *, period: str = "1A"):
        by_key = {
            "KEY11111": [
                _FakeHistoryPoint(
                    as_of_datetime=datetime(2026, 6, 20, 0, 0, tzinfo=timezone.utc),
                    equity=Decimal("1100.25"),
                    profit_loss=Decimal("10.25"),
                    profit_loss_pct=Decimal("0.0094"),
                    base_value=Decimal("1090.00"),
                    timeframe="1D",
                    raw={"source": "one", "period": period},
                )
            ],
            "KEY22222": [
                _FakeHistoryPoint(
                    as_of_datetime=datetime(2026, 6, 20, 0, 0, tzinfo=timezone.utc),
                    equity=Decimal("2200.50"),
                    profit_loss=Decimal("15.00"),
                    profit_loss_pct=Decimal("0.0068"),
                    base_value=Decimal("2185.50"),
                    timeframe="1D",
                    raw={"source": "two", "period": period},
                ),
                _FakeHistoryPoint(
                    as_of_datetime=datetime(2026, 6, 21, 0, 0, tzinfo=timezone.utc),
                    equity=Decimal("2210.50"),
                    profit_loss=Decimal("25.00"),
                    profit_loss_pct=Decimal("0.0114"),
                    base_value=Decimal("2185.50"),
                    timeframe="1D",
                    raw={"source": "two", "period": period},
                ),
            ],
        }
        return by_key[self.key_id]


@override_settings(ACCOUNT_CREDENTIALS_ENCRYPTION_KEY="test-account-credentials-key")
class AccountBrokerCredentialTests(TestCase):
    def setUp(self):
        self.client_obj = Client.objects.create(full_name="Client One")
        self.fund = Fund.objects.create(
            name="Alpaca Fund",
            strategy_code="ALPACA_FUND",
            inception_date=date(2026, 1, 1),
            custodian=Fund.CUSTODIAN_ALPACA,
            custodian_account_id="acct-1",
        )
        self.account = ClientCapitalAccount.objects.create(
            client=self.client_obj,
            fund=self.fund,
            units="10.0",
            nav_per_unit="1.25",
            last_valuation_date=date(2026, 1, 31),
        )

    def test_round_trip_encryption_for_alpaca_credentials(self):
        credential = AccountBrokerCredential(account=self.account, broker=Fund.CUSTODIAN_ALPACA)
        credential.set_alpaca_credentials(key_id="AKIA123456", secret_key="secret-xyz")
        credential.full_clean()
        credential.save()

        self.assertEqual(
            credential.environment,
            AccountBrokerCredential.ENVIRONMENT_PAPER,
        )
        self.assertNotEqual(credential.alpaca_key_id_encrypted, "AKIA123456")
        self.assertNotEqual(credential.alpaca_secret_key_encrypted, "secret-xyz")
        self.assertEqual(credential.get_alpaca_credentials(), ("AKIA123456", "secret-xyz"))

    def test_base_url_uses_environment(self):
        paper_credential = AccountBrokerCredential(
            account=self.account,
            broker=Fund.CUSTODIAN_ALPACA,
            environment=AccountBrokerCredential.ENVIRONMENT_PAPER,
        )
        live_credential = AccountBrokerCredential(
            account=self.account,
            broker=Fund.CUSTODIAN_ALPACA,
            environment=AccountBrokerCredential.ENVIRONMENT_LIVE,
        )

        self.assertEqual(
            paper_credential.get_alpaca_base_url(),
            "https://paper-api.alpaca.markets",
        )
        self.assertEqual(
            live_credential.get_alpaca_base_url(),
            "https://api.alpaca.markets",
        )


@override_settings(ACCOUNT_CREDENTIALS_ENCRYPTION_KEY="test-account-credentials-key")
class AccountPortfolioHistorySyncTests(TestCase):
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

        self.account_one = ClientCapitalAccount.objects.create(
            client=client_one,
            fund=self.fund,
            units="10.0",
            nav_per_unit="1.25",
            last_valuation_date=date(2026, 1, 31),
        )
        self.account_two = ClientCapitalAccount.objects.create(
            client=client_two,
            fund=self.fund,
            units="20.0",
            nav_per_unit="1.25",
            last_valuation_date=date(2026, 1, 31),
        )

        credential_one = AccountBrokerCredential(
            account=self.account_one,
            broker=Fund.CUSTODIAN_ALPACA,
            environment=AccountBrokerCredential.ENVIRONMENT_PAPER,
        )
        credential_one.set_alpaca_credentials(key_id="KEY11111", secret_key="secret-one")
        credential_one.full_clean()
        credential_one.save()

        credential_two = AccountBrokerCredential(
            account=self.account_two,
            broker=Fund.CUSTODIAN_ALPACA,
            environment=AccountBrokerCredential.ENVIRONMENT_LIVE,
        )
        credential_two.set_alpaca_credentials(key_id="KEY22222", secret_key="secret-two")
        credential_two.full_clean()
        credential_two.save()

    @patch(
        "accounts.services.portfolio_history.AlpacaPortfolioHistoryService",
        _FakePortfolioHistoryService,
    )
    def test_sync_uses_each_account_credential_and_persists_history_points(self):
        res = sync_alpaca_account_portfolio_history(fund_id=self.fund.id, period="1M")

        self.assertEqual(res.accounts_processed, 2)
        self.assertEqual(res.points_fetched, 3)
        self.assertEqual(res.created, 3)
        self.assertEqual(res.updated, 0)

        points = list(
            AccountPortfolioHistory.objects.order_by("account_id", "as_of_datetime")
        )
        self.assertEqual(len(points), 3)
        self.assertEqual(points[0].account_id, self.account_one.id)
        self.assertEqual(points[1].account_id, self.account_two.id)
        self.assertEqual(points[2].account_id, self.account_two.id)
        self.assertEqual(points[0].equity, Decimal("1100.25"))
        self.assertEqual(points[2].profit_loss_pct, Decimal("0.011400"))

    @patch(
        "accounts.services.portfolio_history.AlpacaPortfolioHistoryService",
        _FakePortfolioHistoryService,
    )
    def test_repeat_sync_updates_existing_rows(self):
        sync_alpaca_account_portfolio_history(fund_id=self.fund.id, period="1M")
        res = sync_alpaca_account_portfolio_history(fund_id=self.fund.id, period="1M")

        self.assertEqual(res.created, 0)
        self.assertEqual(res.updated, 3)
        self.assertEqual(AccountPortfolioHistory.objects.count(), 3)

    @patch(
        "accounts.services.portfolio_history.AlpacaPortfolioHistoryService",
        _FakePortfolioHistoryService,
    )
    def test_sync_without_scope_processes_all_active_alpaca_credentials(self):
        res = sync_alpaca_account_portfolio_history(period="1M")

        self.assertEqual(res.accounts_processed, 2)
        self.assertEqual(res.points_fetched, 3)
        self.assertEqual(AccountPortfolioHistory.objects.count(), 3)
