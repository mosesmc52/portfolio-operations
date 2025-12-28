from __future__ import annotations

from datetime import date
from typing import Any

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


def run_monthly_reporting_workflow_sync(
    *,
    fund_id: int | None = None,
    benchmark_symbol: str = "SPY",
    include_only_active_clients: bool = True,
    subject_prefix: str = "",
    dry_run_email: bool = False,
) -> dict[str, Any]:
    """
    Run monthly reporting workflow synchronously (no Celery broker required).
    If fund_id is None => all active funds. Otherwise a single fund.
    """
    year, month = _prev_month(date.today())

    if fund_id is not None:
        funds = Fund.objects.filter(id=fund_id)
    else:
        funds = Fund.objects.filter(status=Fund.ACTIVE)

    if not funds.exists():
        raise ValueError("No matching funds found")

    results: list[dict[str, Any]] = []

    for fund in funds:
        # Step 1: snapshot
        snap_res = generate_monthly_snapshot_task.run(
            fund_id=fund.id,
            year=year,
            month=month,
            benchmark_symbol=benchmark_symbol,
            strategy_version=fund.strategy_code,
            model_change=False,
        )
        snapshot_id = snap_res["snapshot_id"]

        # Step 2: artifact
        art_res = generate_monthly_report_artifact_task.run(snapshot_id=snapshot_id)

        # Step 3: email (deterministic via snapshot_id)
        email_res = email_latest_monthly_report_to_clients_task.run(
            fund_id=fund.id,
            snapshot_id=snapshot_id,
            include_only_active_clients=include_only_active_clients,
            subject_prefix=subject_prefix,
            dry_run=dry_run_email,
        )

        results.append(
            {
                "fund_id": fund.id,
                "strategy_code": fund.strategy_code,
                "snapshot": snap_res,
                "artifact": art_res,
                "email": email_res,
            }
        )

    return {
        "year": year,
        "month": month,
        "funds_processed": len(results),
        "results": results,
    }


@shared_task(bind=True)
def run_monthly_reporting_workflow_task(
    self,
    *,
    fund_id: int | None = None,
    benchmark_symbol: str = "SPY",
    include_only_active_clients: bool = True,
    subject_prefix: str = "",
    dry_run_email: bool = False,
) -> dict:
    """
    Celery entrypoint (requires broker). This enqueues per-fund chains.
    Use the management command with --async to call this.
    """
    year, month = _prev_month(date.today())

    if fund_id is not None:
        funds = Fund.objects.filter(id=fund_id)
    else:
        funds = Fund.objects.filter(status=Fund.ACTIVE)

    if not funds.exists():
        raise ValueError("No matching funds found")

    launched = []

    for fund in funds:
        workflow = chain(
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
        ar = workflow.apply_async()
        launched.append(
            {
                "fund_id": fund.id,
                "strategy_code": fund.strategy_code,
                "chain_task_id": ar.id,
            }
        )

    return {
        "queued": True,
        "year": year,
        "month": month,
        "funds_processed": len(launched),
        "chains": launched,
    }


@shared_task
def _adapter_generate_artifact_from_snapshot_result(snapshot_result: dict) -> dict:
    snapshot_id = snapshot_result.get("snapshot_id")
    if not snapshot_id:
        raise ValueError(f"snapshot_result missing snapshot_id: {snapshot_result}")
    return generate_monthly_report_artifact_task.run(snapshot_id=snapshot_id)


@shared_task
def _adapter_email_clients_from_artifact_result(
    artifact_result: dict,
    *,
    include_only_active_clients: bool = True,
    subject_prefix: str = "",
    dry_run_email: bool = False,
) -> dict:
    snapshot_id = artifact_result.get("snapshot_id")
    fund_id = artifact_result.get("fund_id")
    if not snapshot_id or not fund_id:
        raise ValueError(
            f"artifact_result missing snapshot_id/fund_id: {artifact_result}"
        )

    return email_latest_monthly_report_to_clients_task.run(
        fund_id=fund_id,
        snapshot_id=snapshot_id,
        include_only_active_clients=include_only_active_clients,
        subject_prefix=subject_prefix,
        dry_run=dry_run_email,
    )
