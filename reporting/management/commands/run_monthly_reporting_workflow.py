from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError
from workflows.tasks import (
    run_monthly_reporting_workflow_sync,
    run_monthly_reporting_workflow_task,
)


class Command(BaseCommand):
    help = "Run monthly reporting workflow (snapshot → report → email). Sync by default (no Redis)."

    def add_arguments(self, parser):
        parser.add_argument("--fund-id", type=int, help="Run for a single fund only")
        parser.add_argument("--benchmark", type=str, default="SPY")
        parser.add_argument("--subject-prefix", type=str, default="")
        parser.add_argument("--dry-run-email", action="store_true")
        parser.add_argument(
            "--include-only-active-clients", action="store_true", default=True
        )
        parser.add_argument(
            "--async",
            dest="run_async",
            action="store_true",
            help="Queue to Celery (requires broker such as Redis).",
        )

    def handle(self, *args, **opts):
        kwargs = {
            "fund_id": opts.get("fund_id"),
            "benchmark_symbol": opts["benchmark"],
            "subject_prefix": opts["subject_prefix"],
            "include_only_active_clients": opts["include_only_active_clients"],
            "dry_run_email": opts["dry_run_email"],
        }

        try:
            if opts["run_async"]:
                ar = run_monthly_reporting_workflow_task.delay(**kwargs)
                self.stdout.write(
                    json.dumps({"queued": True, "task_id": ar.id, **kwargs}, indent=2)
                )
                self.stdout.write(
                    self.style.SUCCESS("Monthly workflow queued (async).")
                )
            else:
                res = run_monthly_reporting_workflow_sync(**kwargs)
                self.stdout.write(json.dumps(res, indent=2))
                self.stdout.write(
                    self.style.SUCCESS("Monthly workflow completed (sync).")
                )
        except Exception as e:
            raise CommandError(str(e))
