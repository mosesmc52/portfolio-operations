from __future__ import annotations

from datetime import date

from celery import chain, shared_task
from funds.models import Fund
from performance.tasks import generate_monthly_snapshot_task
from reporting.tasks import (
    email_latest_monthly_report_to_clients_task,
    generate_monthly_report_artifact_task,
)


def _prev_month(today: date) -> tuple[int, int]:
    if today.month == 1:
        return today.year - 1, 12
    return today.year, today.month - 1


@shared_task(bind=True)
def run_monthly_reporting_workflow_task(
    self,
    *,
    benchmark_symbol: str = "SPY",
    include_only_active_clients: bool = True,
    subject_prefix: str = "",
    dry_run_email: bool = False,
) -> dict:
    """
    Orchestrates monthly reporting for ALL ACTIVE FUNDS.
    """
    year, month = _prev_month(date.today())

    funds = Fund.objects.filter(status=Fund.ACTIVE)

    launched = []

    for fund in funds:
        c = chain(
            generate_monthly_snapshot_task.s(
                fund_id=fund.id,
                year=year,
                month=month,
                benchmark_symbol=benchmark_symbol,
                strategy_version=fund.strategy_code,
                model_change=False,
            ),
            _adapter_generate_artifact_from_snapshot_result.s(),
            _adapter_email_clients_from_artifact_result.s(
                include_only_active_clients=include_only_active_clients,
                subject_prefix=subject_prefix,
                dry_run_email=dry_run_email,
            ),
        )
        result = c.apply_async()
        launched.append(
            {
                "fund_id": fund.id,
                "strategy_code": fund.strategy_code,
                "chain_task_id": result.id,
            }
        )

    return {
        "year": year,
        "month": month,
        "funds_processed": len(launched),
        "chains": launched,
    }
