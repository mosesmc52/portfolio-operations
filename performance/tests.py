from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from accounts.models import (
    AccountBrokerCredential,
    AccountPortfolioHistory,
    CapitalFlow,
    ClientCapitalAccount,
)
from clients.models import Client
from django.test import TestCase, override_settings
from funds.models import Fund
from performance.models import NAVSnapshot
from performance.services.nav import compute_and_save_navsnapshot
from performance.services.nav_backfill import backfill_navsnapshots_from_portfolio_history


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


@override_settings(ACCOUNT_CREDENTIALS_ENCRYPTION_KEY="test-account-credentials-key")
class NavBackfillFromPortfolioHistoryTests(TestCase):
    def setUp(self):
        self.fund = Fund.objects.create(
            name="Trend Fund",
            strategy_code="ETF_TREND_VT",
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
            nav_per_unit="1.00",
            last_valuation_date=date(2026, 2, 2),
        )
        self.account_two = ClientCapitalAccount.objects.create(
            client=client_two,
            fund=self.fund,
            units="20.0",
            nav_per_unit="1.00",
            last_valuation_date=date(2026, 2, 2),
        )

        CapitalFlow.objects.create(
            client=client_one,
            fund=self.fund,
            flow_type=CapitalFlow.TYPE_SUBSCRIPTION,
            amount=Decimal("10.00"),
            nav_at_flow=Decimal("1.00"),
            units_delta=Decimal("10.00000000"),
            flow_date=date(2026, 2, 1),
            external_ref="c1-sub-1",
        )
        CapitalFlow.objects.create(
            client=client_two,
            fund=self.fund,
            flow_type=CapitalFlow.TYPE_SUBSCRIPTION,
            amount=Decimal("20.00"),
            nav_at_flow=Decimal("1.00"),
            units_delta=Decimal("20.00000000"),
            flow_date=date(2026, 2, 2),
            external_ref="c2-sub-1",
        )

        AccountPortfolioHistory.objects.create(
            account=self.account_one,
            broker=Fund.CUSTODIAN_ALPACA,
            as_of_date=date(2026, 2, 1),
            as_of_datetime="2026-02-01T00:00:00Z",
            timeframe="1D",
            equity=Decimal("10.00"),
            profit_loss=Decimal("0.00"),
            profit_loss_pct=Decimal("0.000000"),
            base_value=Decimal("10.00"),
            raw={},
        )
        AccountPortfolioHistory.objects.create(
            account=self.account_one,
            broker=Fund.CUSTODIAN_ALPACA,
            as_of_date=date(2026, 2, 2),
            as_of_datetime="2026-02-02T00:00:00Z",
            timeframe="1D",
            equity=Decimal("11.00"),
            profit_loss=Decimal("1.00"),
            profit_loss_pct=Decimal("0.100000"),
            base_value=Decimal("10.00"),
            raw={},
        )
        AccountPortfolioHistory.objects.create(
            account=self.account_two,
            broker=Fund.CUSTODIAN_ALPACA,
            as_of_date=date(2026, 2, 2),
            as_of_datetime="2026-02-02T00:00:00Z",
            timeframe="1D",
            equity=Decimal("22.00"),
            profit_loss=Decimal("2.00"),
            profit_loss_pct=Decimal("0.100000"),
            base_value=Decimal("20.00"),
            raw={},
        )

    def test_backfill_navsnapshots_from_portfolio_history(self):
        res = backfill_navsnapshots_from_portfolio_history(
            fund_id=self.fund.id,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 2),
        )

        self.assertEqual(res.dates_considered, 2)
        self.assertEqual(res.created, 2)
        self.assertEqual(res.updated, 0)
        self.assertEqual(res.skipped_no_units, 0)

        snaps = {
            snap.date: snap
            for snap in NAVSnapshot.objects.filter(fund=self.fund).order_by("date")
        }
        self.assertEqual(snaps[date(2026, 2, 1)].total_units, Decimal("10.00000000"))
        self.assertEqual(snaps[date(2026, 2, 1)].aum, Decimal("10.00"))
        self.assertEqual(snaps[date(2026, 2, 1)].nav_per_unit, Decimal("1.00000000"))
        self.assertEqual(snaps[date(2026, 2, 2)].total_units, Decimal("30.00000000"))
        self.assertEqual(snaps[date(2026, 2, 2)].aum, Decimal("33.00"))
        self.assertEqual(snaps[date(2026, 2, 2)].nav_per_unit, Decimal("1.10000000"))
