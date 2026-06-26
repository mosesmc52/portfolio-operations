from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from accounts.models import AccountPortfolioHistory, CapitalFlow, ClientCapitalAccount
from django.db import transaction
from funds.models import Fund
from performance.models import NAVSnapshot

NAV_Q = Decimal("0.00000001")
USD_Q = Decimal("0.01")


def _q_nav(x: Decimal) -> Decimal:
    return x.quantize(NAV_Q, rounding=ROUND_HALF_UP)


def _q_usd(x: Decimal) -> Decimal:
    return x.quantize(USD_Q, rounding=ROUND_HALF_UP)


@dataclass
class NavBackfillResult:
    fund_id: int
    fund_strategy_code: str
    start_date: date | None
    end_date: date | None
    dates_considered: int
    created: int
    updated: int
    skipped_no_units: int


def _build_units_history_by_account(
    *, fund: Fund, account_ids: set[int], relevant_dates: list[date]
) -> dict[int, dict[date, Decimal]]:
    if not relevant_dates:
        return {}

    start_date = relevant_dates[0]
    end_date = relevant_dates[-1]

    accounts = {
        acct.id: acct
        for acct in ClientCapitalAccount.objects.filter(id__in=account_ids, fund=fund)
    }
    # CapitalFlow links to client+fund, not account directly. Resolve through account client.
    flows = list(
        CapitalFlow.objects.filter(
            fund=fund,
            client_id__in=[acct.client_id for acct in accounts.values()],
            flow_date__lte=end_date,
        )
        .order_by("client_id", "flow_date", "id")
        .values("client_id", "flow_date", "units_delta")
    )

    flows_by_client: dict[int, list[dict]] = {}
    for flow in flows:
        flows_by_client.setdefault(int(flow["client_id"]), []).append(flow)

    units_history: dict[int, dict[date, Decimal]] = {}
    for account_id, account in accounts.items():
        client_flows = flows_by_client.get(account.client_id, [])
        current_units = Decimal("0")
        per_date: dict[date, Decimal] = {}
        idx = 0

        if not client_flows:
            fallback_units = Decimal(account.units or 0)
            for d in relevant_dates:
                per_date[d] = fallback_units
            units_history[account_id] = per_date
            continue

        for d in relevant_dates:
            while idx < len(client_flows) and client_flows[idx]["flow_date"] <= d:
                current_units += Decimal(client_flows[idx]["units_delta"])
                idx += 1
            per_date[d] = current_units

        units_history[account_id] = per_date

    return units_history


def backfill_navsnapshots_from_portfolio_history(
    *,
    fund_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> NavBackfillResult:
    fund = Fund.objects.get(id=fund_id)

    hist_qs = AccountPortfolioHistory.objects.filter(
        account__fund=fund,
        timeframe="1D",
    )
    if start_date is not None:
        hist_qs = hist_qs.filter(as_of_date__gte=start_date)
    if end_date is not None:
        hist_qs = hist_qs.filter(as_of_date__lte=end_date)

    rows = list(
        hist_qs.order_by("as_of_date", "account_id").values(
            "account_id", "as_of_date", "equity"
        )
    )
    if not rows:
        return NavBackfillResult(
            fund_id=fund.id,
            fund_strategy_code=fund.strategy_code,
            start_date=start_date,
            end_date=end_date,
            dates_considered=0,
            created=0,
            updated=0,
            skipped_no_units=0,
        )

    dates = sorted({row["as_of_date"] for row in rows})
    account_ids = {int(row["account_id"]) for row in rows}
    units_history = _build_units_history_by_account(
        fund=fund,
        account_ids=account_ids,
        relevant_dates=dates,
    )

    equity_by_date: dict[date, Decimal] = {}
    account_presence_by_date: dict[date, set[int]] = {}
    for row in rows:
        d = row["as_of_date"]
        equity_by_date[d] = equity_by_date.get(d, Decimal("0")) + Decimal(row["equity"])
        account_presence_by_date.setdefault(d, set()).add(int(row["account_id"]))

    created = 0
    updated = 0
    skipped_no_units = 0

    with transaction.atomic():
        for d in dates:
            total_units = Decimal("0")
            for account_id in account_presence_by_date.get(d, set()):
                total_units += units_history.get(account_id, {}).get(d, Decimal("0"))

            if total_units <= 0:
                skipped_no_units += 1
                continue

            aum = _q_usd(equity_by_date[d])
            nav_per_unit = _q_nav(aum / total_units)
            _, was_created = NAVSnapshot.objects.update_or_create(
                fund=fund,
                date=d,
                defaults={
                    "nav_per_unit": nav_per_unit,
                    "total_units": total_units.quantize(NAV_Q, rounding=ROUND_HALF_UP),
                    "aum": aum,
                    "cash_balance": None,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

    return NavBackfillResult(
        fund_id=fund.id,
        fund_strategy_code=fund.strategy_code,
        start_date=start_date,
        end_date=end_date,
        dates_considered=len(dates),
        created=created,
        updated=updated,
        skipped_no_units=skipped_no_units,
    )
