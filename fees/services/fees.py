from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from fees.models import FundExpense
from funds.models import Fund
from performance.models import NAVSnapshot

USD_Q = Decimal("0.01")


def _q_usd(x: Decimal) -> Decimal:
    return x.quantize(USD_Q, rounding=ROUND_HALF_UP)


def accrue_management_fee_for_day(
    *, fund: Fund, as_of: date, annual_rate: Decimal
) -> FundExpense:
    """
    Accrue a daily management fee based on that day's AUM (from NAVSnapshot.aum).
    Requires NAVSnapshot for as_of date.
    """
    snap = NAVSnapshot.objects.filter(fund=fund, date=as_of).first()
    if not snap:
        raise ValueError(f"No NAVSnapshot for fund={fund.strategy_code} date={as_of}")

    aum = Decimal(snap.aum)
    if aum < 0:
        raise ValueError("AUM must be >= 0")

    daily_fee = _q_usd(aum * (annual_rate / Decimal("365")))

    with transaction.atomic():
        obj, _ = FundExpense.objects.update_or_create(
            fund=fund,
            expense_type=FundExpense.TYPE_MGMT_FEE,
            as_of_date=as_of,
            defaults={
                "amount": daily_fee,
                "is_paid": False,
            },
        )
        return obj
