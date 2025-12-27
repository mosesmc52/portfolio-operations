from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from accounts.models import ClientCapitalAccount
from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from performance.models import MonthlySnapshot, NAVSnapshot
from performance.services.nav import compute_and_save_navsnapshot
from reporting.models import MonthlyReportArtifact
from reporting.services.monthly_reporting_service import MonthlyReportingService
from services.market_data.price_provider import YFinancePriceProvider


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def compute_navsnapshot_task(self, *, fund_id: int) -> dict:
    snap = compute_and_save_navsnapshot(fund_id=fund_id)
    return {
        "fund_id": fund_id,
        "date": str(snap.date),
        "nav_per_unit": str(snap.nav_per_unit),
        "aum": str(snap.aum),
        "total_units": str(snap.total_units),
    }


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def _get_latest_nav_on_or_before(*, fund_id: int, d: date):
    return (
        NAVSnapshot.objects.filter(fund_id=fund_id, date__lte=d)
        .order_by("-date")
        .first()
    )


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def generate_monthly_snapshot_task(
    self,
    *,
    fund_id: int,
    year: int,
    month: int,
    benchmark_symbol: str = "SPY",
    strategy_version: str | None = None,
    model_change: bool = False,
) -> dict:
    """
    Compute and upsert MonthlySnapshot (canonical monthly metrics).
    Returns snapshot_id.
    """
    period_start, period_end = _month_bounds(year, month)
    as_of_month = period_end

    nav_bom_obj = _get_latest_nav_on_or_before(fund_id=fund_id, d=period_start)
    nav_eom_obj = _get_latest_nav_on_or_before(fund_id=fund_id, d=period_end)

    if not nav_bom_obj or not nav_eom_obj:
        raise ValueError(
            f"Missing NAVSnapshot boundaries for fund_id={fund_id}. "
            f"Need NAV on/before {period_start} and {period_end}."
        )

    nav_bom = Decimal(nav_bom_obj.nav_per_unit)
    nav_eom = Decimal(nav_eom_obj.nav_per_unit)
    if nav_bom <= 0:
        raise ValueError("nav_bom must be > 0")

    fund_return = (nav_eom / nav_bom) - Decimal("1")

    total_units = ClientCapitalAccount.objects.filter(fund_id=fund_id).aggregate(
        s=Coalesce(Sum("units"), Decimal("0"))
    ).get("s") or Decimal("0")
    aum_eom = (nav_eom * total_units).quantize(Decimal("0.01"))

    # Benchmark return (optional)
    benchmark_return = None
    excess_return = None
    try:
        price_provider = YFinancePriceProvider()
        bench = price_provider.get_daily_close(
            symbol=benchmark_symbol,
            start=period_start,
            end=period_end + timedelta(days=1),
        )
        if len(bench.close) >= 2 and bench.close[0] > 0:
            benchmark_return = Decimal(str((bench.close[-1] / bench.close[0]) - 1.0))
            excess_return = fund_return - benchmark_return
    except Exception:
        # Keep snapshot generation resilient even if benchmark fetch fails
        benchmark_return = None
        excess_return = None

    if not strategy_version:
        strategy_version = getattr(settings, "STRATEGY_VERSION", "unknown")

    metrics_json = {}  # expand later (drawdown/vol/sharpe etc.)

    with transaction.atomic():
        snap, _ = MonthlySnapshot.objects.update_or_create(
            fund_id=fund_id,
            as_of_month=as_of_month,
            defaults={
                "nav_bom": nav_bom,
                "nav_eom": nav_eom,
                "aum_eom": aum_eom,
                "fund_return": fund_return,
                "benchmark_symbol": benchmark_symbol,
                "benchmark_return": benchmark_return,
                "excess_return": excess_return,
                "strategy_version": strategy_version,
                "model_change": model_change,
                "metrics_json": metrics_json,
            },
        )

    return {
        "snapshot_id": snap.id,
        "fund_id": fund_id,
        "as_of_month": str(as_of_month),
        "fund_return": str(fund_return),
        "benchmark_return": (
            str(benchmark_return) if benchmark_return is not None else None
        ),
    }
