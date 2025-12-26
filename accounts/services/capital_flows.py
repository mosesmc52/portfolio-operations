from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from accounts.models import CapitalFlow, ClientCapitalAccount
from django.db import transaction
from performance.models import NAVSnapshot

UNITS_Q = Decimal("0.00000001")
USD_Q = Decimal("0.01")


def _q_units(x: Decimal) -> Decimal:
    return x.quantize(UNITS_Q, rounding=ROUND_HALF_UP)


def _q_usd(x: Decimal) -> Decimal:
    return x.quantize(USD_Q, rounding=ROUND_HALF_UP)


def _get_nav_for_flow_date(
    *, fund, flow_date: date, pricing_policy: str
) -> NAVSnapshot:
    """
    pricing_policy:
      - "EXACT": require NAVSnapshot exactly on flow_date
      - "PREV":  use most recent NAVSnapshot on or before flow_date
    """
    if pricing_policy == "EXACT":
        nav = NAVSnapshot.objects.filter(fund=fund, date=flow_date).first()
        if not nav:
            raise ValueError(f"No NAVSnapshot for fund={fund} date={flow_date}")
        return nav

    if pricing_policy == "PREV":
        nav = (
            NAVSnapshot.objects.filter(fund=fund, date__lte=flow_date)
            .order_by("-date")
            .first()
        )
        if not nav:
            raise ValueError(f"No NAVSnapshot on or before {flow_date} for fund={fund}")
        return nav

    raise ValueError(f"Invalid pricing_policy: {pricing_policy}")


def apply_capital_flow(
    *,
    client,
    fund,
    flow_type: str,
    flow_date: date,
    amount: Decimal,
    external_ref: str,
    pricing_policy: str = "PREV",  # <-- default to PREV to avoid this error
    allow_over_redeem: bool = False,
) -> CapitalFlow:
    if not external_ref:
        raise ValueError("external_ref is required for idempotency")

    amount = _q_usd(Decimal(amount))
    if amount <= 0:
        raise ValueError("Amount must be > 0")

    with transaction.atomic():
        existing = CapitalFlow.objects.filter(
            fund=fund, client=client, external_ref=external_ref
        ).first()
        if existing:
            return existing

        nav = _get_nav_for_flow_date(
            fund=fund, flow_date=flow_date, pricing_policy=pricing_policy
        )
        nav_per_unit = Decimal(nav.nav_per_unit)
        if nav_per_unit <= 0:
            raise ValueError("NAV per unit must be > 0")

        units = _q_units(amount / nav_per_unit)

        if flow_type == CapitalFlow.TYPE_SUBSCRIPTION:
            units_delta = units
        elif flow_type == CapitalFlow.TYPE_REDEMPTION:
            units_delta = -units
        else:
            raise ValueError(f"Invalid flow_type: {flow_type}")

        acct, _ = ClientCapitalAccount.objects.select_for_update().get_or_create(
            client=client,
            fund=fund,
            defaults={
                "units": Decimal("0"),
                "nav_per_unit": nav_per_unit,
                "last_valuation_date": nav.date,
            },
        )

        current_units = Decimal(acct.units or 0)
        if flow_type == CapitalFlow.TYPE_REDEMPTION and (not allow_over_redeem):
            if current_units + units_delta < Decimal("0"):
                raise ValueError(
                    f"Redemption exceeds units. current_units={current_units}, units_to_redeem={-units_delta}"
                )

        flow = CapitalFlow.objects.create(
            client=client,
            fund=fund,
            flow_type=flow_type,
            amount=amount,
            nav_at_flow=nav_per_unit,
            units_delta=units_delta,
            flow_date=flow_date,
            external_ref=external_ref,
        )

        acct.units = _q_units(current_units + units_delta)
        acct.nav_per_unit = nav_per_unit
        acct.last_valuation_date = nav.date  # <-- note: the valuation date used
        acct.save(update_fields=["units", "nav_per_unit", "last_valuation_date"])

        return flow
