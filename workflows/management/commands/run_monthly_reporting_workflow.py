from __future__ import annotations

import json
from datetime import date
from typing import Any

# Celery primitives
from celery import chain
from django.core.management.base import BaseCommand, CommandError
from portfolio.models import Fund  # <-- UPDATE import path to your Fund model

# Import the tasks/adapters used in the workflow
from portfolio.tasks.reporting import (  # <-- UPDATE module path(s)
    _adapter_email_clients_from_artifact_result,
    _adapter_generate_artifact_from_snapshot_result,
    generate_monthly_snapshot_task,
)

# If _prev_month lives elsewhere, update this import
from portfolio.utils.dates import _prev_month  # <-- UPDATE


class Command(BaseCommand):
    help = (
        "Run the monthly reporting workflow (previous month by default). "
        "Can run inline (no broker) or async via Celery."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--fund-id", type=int, default=None, help="Run for a single fund ID"
        )
        parser.add_argument("--benchmark-symbol", type=str, default="SPY")
        parser.add_argument(
            "--include-only-active-clients",
            action="store_true",
            default=True,
            help="Email only active clients (default: true)",
        )
        parser.add_argument(
            "--include-inactive-clients",
            action="store_true",
            default=False,
            help="Override to email inactive clients too",
        )
        parser.add_argument("--subject-prefix", type=str, default="")
        parser.add_argument("--dry-run-email", action="store_true", default=False)

        parser.add_argument(
            "--async",
            dest="run_async",
            action="store_true",
            default=False,
            help="Queue Celery chains with apply_async (requires broker/worker)",
        )

        parser.add_argument(
            "--year",
            type=int,
            default=None,
            help="Override year for the snapshot (default: previous month year)",
        )
        parser.add_argument(
            "--month",
            type=int,
            default=None,
            help="Override month for the snapshot (1-12) (default: previous month)",
        )

        parser.add_argument(
            "--json", action="store_true", default=False, help="Print JSON output only"
        )

    def handle(self, *args, **opts):
        fund_id: int | None = opts["fund_id"]
        benchmark_symbol: str = opts["benchmark_symbol"]
        subject_prefix: str = opts["subject_prefix"]
        dry_run_email: bool = bool(opts["dry_run_email"])
        run_async: bool = bool(opts["run_async"])

        include_only_active_clients: bool = True
        if opts["include_inactive_clients"]:
            include_only_active_clients = False
        else:
            include_only_active_clients = bool(opts["include_only_active_clients"])

        # Determine period (previous month by default)
        if opts["year"] is not None or opts["month"] is not None:
            if opts["year"] is None or opts["month"] is None:
                raise CommandError("--year and --month must be provided together")
            year = int(opts["year"])
            month = int(opts["month"])
            if month < 1 or month > 12:
                raise CommandError("--month must be in 1..12")
        else:
            year, month = _prev_month(date.today())

        # Select funds
        if fund_id is not None:
            funds = Fund.objects.filter(id=fund_id)
        else:
            funds = Fund.objects.filter(status=Fund.ACTIVE)

        if not funds.exists():
            raise CommandError("No matching funds found")

        launched: list[dict[str, Any]] = []

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

            if run_async:
                # Broker/worker required
                ar = workflow.apply_async()
                launched.append(
                    {
                        "fund_id": fund.id,
                        "strategy_code": fund.strategy_code,
                        "mode": "async",
                        "chain_task_id": ar.id,
                    }
                )
            else:
                # Inline execution (no broker needed)
                # This runs sequentially in-process; exceptions propagate.
                res = workflow.apply()
                launched.append(
                    {
                        "fund_id": fund.id,
                        "strategy_code": fund.strategy_code,
                        "mode": "inline",
                        "result_type": type(res).__name__,
                    }
                )

        payload = {
            "queued": run_async,
            "year": year,
            "month": month,
            "funds_processed": len(launched),
            "chains": launched,
            "benchmark_symbol": benchmark_symbol,
            "include_only_active_clients": include_only_active_clients,
            "subject_prefix": subject_prefix,
            "dry_run_email": dry_run_email,
        }

        if opts["json"]:
            self.stdout.write(json.dumps(payload, indent=2))
        else:
            self.stdout.write(
                f"Monthly reporting workflow complete: {payload['funds_processed']} fund(s), "
                f"{year}-{month:02d}, mode={'async' if run_async else 'inline'}"
            )
            self.stdout.write(json.dumps(payload, indent=2))

        return None
