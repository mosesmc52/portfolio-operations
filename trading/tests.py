from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import patch

from accounts.models import AccountBrokerCredential, ClientCapitalAccount
from clients.models import Client
from django.test import TestCase, override_settings
from funds.models import Fund
from services.brokers.alpaca_orders_service import AlpacaOrderFill
from trading.models import TradeFill
from trading.sync import sync_alpaca_filled_orders_last_days


class _FakeOrdersService:
    def __init__(self, key_id: str, secret_key: str, base_url: str):
        self.key_id = key_id
        self.secret_key = secret_key
        self.base_url = base_url

    def list_filled_orders_last_days(self, *, days: int, limit: int = 500):
        by_key = {
            "KEY11111": [
                AlpacaOrderFill(
                    external_order_id="order-1",
                    external_fill_id="fill-shared",
                    symbol="SPY",
                    side="buy",
                    filled_qty=2.0,
                    filled_avg_price=500.0,
                    filled_at=datetime(2026, 6, 1, 14, 30, tzinfo=timezone.utc),
                    raw={"id": "order-1", "account_key": self.key_id},
                )
            ],
            "KEY22222": [
                AlpacaOrderFill(
                    external_order_id="order-2",
                    external_fill_id="fill-shared",
                    symbol="QQQ",
                    side="sell",
                    filled_qty=1.0,
                    filled_avg_price=400.0,
                    filled_at=datetime(2026, 6, 2, 14, 30, tzinfo=timezone.utc),
                    raw={"id": "order-2", "account_key": self.key_id},
                )
            ],
        }
        return by_key[self.key_id]


@override_settings(ACCOUNT_CREDENTIALS_ENCRYPTION_KEY="test-account-credentials-key")
class TradingSyncTests(TestCase):
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

    @patch("trading.sync.AlpacaOrdersService", _FakeOrdersService)
    def test_sync_uses_each_account_credential_and_scopes_fill_uniqueness_by_account(self):
        res = sync_alpaca_filled_orders_last_days(fund_id=self.fund.id, days=7, limit=100)

        self.assertEqual(res.accounts_processed, 2)
        self.assertEqual(res.fetched, 2)
        self.assertEqual(res.created, 2)
        self.assertEqual(res.updated, 0)

        fills = list(TradeFill.objects.order_by("account_id"))
        self.assertEqual(len(fills), 2)
        self.assertEqual(fills[0].account_id, self.account_one.id)
        self.assertEqual(fills[1].account_id, self.account_two.id)
        self.assertEqual(fills[0].external_fill_id, "fill-shared")
        self.assertEqual(fills[1].external_fill_id, "fill-shared")

    @patch("trading.sync.AlpacaOrdersService", _FakeOrdersService)
    def test_repeat_sync_updates_existing_rows_per_account(self):
        sync_alpaca_filled_orders_last_days(fund_id=self.fund.id, days=7, limit=100)
        res = sync_alpaca_filled_orders_last_days(fund_id=self.fund.id, days=7, limit=100)

        self.assertEqual(res.created, 0)
        self.assertEqual(res.updated, 2)
        self.assertEqual(TradeFill.objects.count(), 2)
