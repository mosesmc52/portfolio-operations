# apps/trading/sync.py
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal

from accounts.models import AccountBrokerCredential
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from funds.models import Fund
from services.brokers.alpaca_orders_service import AlpacaOrdersService
from trading.models import TradeFill


@dataclass
class SyncResult:
    fund_id: int
    fund_strategy_code: str
    days: int
    accounts_processed: int
    fetched: int
    created: int
    updated: int


def sync_alpaca_filled_orders_last_days(
    *, fund_id: int, days: int, limit: int = 500
) -> SyncResult:
    """
    Pull filled orders from each active Alpaca account tied to the fund and
    upsert into TradeFill. One TradeFill row per account-scoped filled order.
    """
    fund = Fund.objects.get(id=fund_id)

    if fund.custodian != Fund.CUSTODIAN_ALPACA:
        raise ValueError("Fund custodian must be ALPACA.")
    if fund.status != Fund.STATUS_ACTIVE:
        raise ValueError("Fund must be ACTIVE.")

    credentials = list(
        AccountBrokerCredential.objects.select_related("account", "account__fund")
        .filter(
            account__fund=fund,
            broker=Fund.CUSTODIAN_ALPACA,
            is_active=True,
        )
        .order_by("id")
    )

    if not credentials:
        raise ValueError(
            f"No active Alpaca account credentials configured for fund={fund.strategy_code}."
        )

    accounts_processed = 0
    fetched = 0
    created = 0
    updated = 0

    with transaction.atomic():
        for credential in credentials:
            key_id, secret_key = credential.get_alpaca_credentials()
            svc = AlpacaOrdersService(
                key_id=key_id,
                secret_key=secret_key,
                base_url=credential.get_alpaca_base_url(),
            )
            fills = svc.list_filled_orders_last_days(days=days, limit=limit)
            accounts_processed += 1
            fetched += len(fills)

            for f in fills:
                qty = Decimal(str(f.filled_qty))
                price = Decimal(str(f.filled_avg_price))
                notional = (qty * price).quantize(Decimal("0.01"))

                safe_raw = json.loads(json.dumps(f.raw, cls=DjangoJSONEncoder))
                _, was_created = TradeFill.objects.update_or_create(
                    account=credential.account,
                    external_fill_id=f.external_fill_id,
                    defaults={
                        "fund": fund,
                        "broker": Fund.CUSTODIAN_ALPACA,
                        "symbol": f.symbol,
                        "side": f.side,
                        "qty": qty,
                        "price": price,
                        "notional": notional,
                        "filled_at": f.filled_at,
                        "raw": safe_raw,
                    },
                )

                if was_created:
                    created += 1
                else:
                    updated += 1

    return SyncResult(
        fund_id=fund.id,
        fund_strategy_code=fund.strategy_code,
        days=days,
        accounts_processed=accounts_processed,
        fetched=fetched,
        created=created,
        updated=updated,
    )
