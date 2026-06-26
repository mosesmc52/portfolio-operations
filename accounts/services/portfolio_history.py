from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from accounts.models import AccountBrokerCredential, AccountPortfolioHistory
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from funds.models import Fund
from services.brokers.alpaca_portfolio_history_service import (
    AlpacaPortfolioHistoryService,
)
import json


@dataclass
class AccountPortfolioHistorySyncResult:
    accounts_processed: int
    points_fetched: int
    created: int
    updated: int


def sync_alpaca_account_portfolio_history(
    *,
    fund_id: int | None = None,
    account_id: int | None = None,
    period: str = "1A",
) -> AccountPortfolioHistorySyncResult:
    if fund_id is not None and account_id is not None:
        raise ValueError("Provide at most one of fund_id or account_id.")

    filters = {
        "broker": Fund.CUSTODIAN_ALPACA,
        "is_active": True,
    }
    if fund_id is not None:
        filters["account__fund_id"] = fund_id
    if account_id is not None:
        filters["account_id"] = account_id

    credentials = list(
        AccountBrokerCredential.objects.select_related("account", "account__fund")
        .filter(**filters)
        .order_by("id")
    )
    if not credentials:
        raise ValueError("No active Alpaca account credentials found for the requested scope.")

    accounts_processed = 0
    points_fetched = 0
    created = 0
    updated = 0

    with transaction.atomic():
        for credential in credentials:
            key_id, secret_key = credential.get_alpaca_credentials()
            svc = AlpacaPortfolioHistoryService(
                key_id=key_id,
                secret_key=secret_key,
                base_url=credential.get_alpaca_base_url(),
            )
            points = svc.get_daily_portfolio_history(period=period)
            accounts_processed += 1
            points_fetched += len(points)

            for point in points:
                safe_raw = json.loads(json.dumps(point.raw, cls=DjangoJSONEncoder))
                _, was_created = AccountPortfolioHistory.objects.update_or_create(
                    account=credential.account,
                    as_of_datetime=point.as_of_datetime,
                    timeframe=point.timeframe,
                    defaults={
                        "broker": Fund.CUSTODIAN_ALPACA,
                        "as_of_date": point.as_of_datetime.date(),
                        "equity": point.equity.quantize(Decimal("0.01")),
                        "profit_loss": point.profit_loss.quantize(Decimal("0.01")),
                        "profit_loss_pct": point.profit_loss_pct,
                        "base_value": point.base_value.quantize(Decimal("0.01"))
                        if point.base_value is not None
                        else None,
                        "raw": safe_raw,
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

    return AccountPortfolioHistorySyncResult(
        accounts_processed=accounts_processed,
        points_fetched=points_fetched,
        created=created,
        updated=updated,
    )
