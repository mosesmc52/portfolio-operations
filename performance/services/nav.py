from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from accounts.models import ClientCapitalAccount
from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from funds.models import Fund
from performance.models import NAVSnapshot
from services.brokers.alpaca_valuation_service import AlpacaValuationService

NAV_Q = Decimal("0.00000001")
USD_Q = Decimal("0.01")


def _q_nav(x: Decimal) -> Decimal:
    return x.quantize(NAV_Q, rounding=ROUND_HALF_UP)


def _q_usd(x: Decimal) -> Decimal:
    return x.quantize(USD_Q, rounding=ROUND_HALF_UP)


def compute_and_save_navsnapshot(
    *, fund_id: int, as_of: date | None = None
) -> NAVSnapshot:
    fund = Fund.objects.get(id=fund_id)

    if fund.custodian != Fund.CUSTODIAN_ALPACA:
        raise ValueError("This NAV function is for Alpaca funds only.")
    if fund.status != Fund.STATUS_ACTIVE:
        raise ValueError("Fund must be ACTIVE to compute NAV.")

    as_of = as_of or timezone.now().date()

    # Total units from ledger (recommended source of truth)
    total_units = ClientCapitalAccount.objects.filter(fund=fund).aggregate(
        s=Sum("units")
    ).get("s") or Decimal("0")

    if total_units <= 0:
        # You can decide to allow NAV snapshots when no units exist; I recommend hard fail.
        raise ValueError(
            "Total units <= 0. Create an initial subscription (CapitalFlow) first."
        )

    svc = AlpacaValuationService(
        key_id=settings.ALPACA_KEY_ID,
        secret_key=settings.ALPACA_SECRET_KEY,
        base_url=settings.ALPACA_BASE_URL,
    )
    val = svc.get_account_valuation()

    aum = _q_usd(val.equity)
    nav_per_unit = _q_nav(aum / total_units)

    with transaction.atomic():
        snap, _ = NAVSnapshot.objects.update_or_create(
            fund=fund,
            date=as_of,
            defaults={
                "nav_per_unit": nav_per_unit,
                "total_units": total_units,
                "aum": aum,
                "cash_balance": _q_usd(val.cash),
            },
        )
        return snap
