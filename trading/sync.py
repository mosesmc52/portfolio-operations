# apps/trading/sync.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from funds.models import Fund
from services.brokers.alpaca_orders_service import AlpacaOrdersService
from trading.models import TradeFill


@dataclass
class SyncResult:
    fund_id: int
    fund_strategy_code: str
    days: int
    fetched: int
    created: int
    updated: int


def sync_alpaca_filled_orders_last_days(
    *, fund_id: int, days: int, limit: int = 500
) -> SyncResult:
    """
    Pull filled orders from Alpaca and upsert into TradeFill.
    One TradeFill row per filled order.
    """
    fund = Fund.objects.get(id=fund_id)

    if fund.custodian != Fund.CUSTODIAN_ALPACA:
        raise ValueError("Fund custodian must be ALPACA.")
    if fund.status != Fund.STATUS_ACTIVE:
        raise ValueError("Fund must be ACTIVE.")

    svc = AlpacaOrdersService(
        key_id=settings.ALPACA_KEY_ID,
        secret_key=settings.ALPACA_SECRET_KEY,
        base_url=settings.ALPACA_BASE_URL,
    )

    fills = svc.list_filled_orders_last_days(days=days, limit=limit)

    created = 0
    updated = 0

    with transaction.atomic():
        for f in fills:
            qty = Decimal(str(f.filled_qty))
            price = Decimal(str(f.filled_avg_price))
            notional = (qty * price).quantize(Decimal("0.01"))

            obj, was_created = TradeFill.objects.update_or_create(
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
                    "raw": f.raw,
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
        fetched=len(fills),
        created=created,
        updated=updated,
    )
