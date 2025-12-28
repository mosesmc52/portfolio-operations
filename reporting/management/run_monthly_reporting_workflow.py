from __future__ import annotations

import json
from django.core.management.base import BaseCommand, CommandError

from reporting.tasks_monthly_workflow import run_monthly_reporting_workflow_task


class Command(BaseCommand):
    help = "Queue the monthly reporting workflow (snapshot -> artifact -> email)."

    def add_arguments(self, parser):
        parser.add_argument("--fund-id", type=int, required=True)
        parser.add_argument("--benchmark", type=str, default="SPY")
        parser.add_argument("--strategy-version", type=str, default=None)
        parser.add_argument("--model-change", action="store_true")
        parser.add_argument("--include-only-active", action="store_true")
        parser.add_argument("--subject-prefix", type=str, default="")
        parser.add_argument("--dry-run-email", action="store_true")

    def handle(self, *args, **opts):
        kwargs = {
            "fund_id": opts["fund_id"],
            "benchmark_symbol": opts["benchmark"],
            "strategy_version": opts["strategy_version"],
            "model_change": bool(opts["model_change"]),
            "include_only_active_clients": bool(opts["include_only_active"]),
            "subject_prefix": opts["subject_prefix"],
            "dry_run_email": bool(opts["dry_run_email"]),
        }

        try:
            res = run_monthly_reporting_workflow_task.delay(**kwargs)
        except Exception as e:
            raise CommandError(str(e))

        self.stdout.write(json.dumps({"queued": True, "task_id": res.id, **kwargs}, indent=2))
        self.stdout.write(self.style.SUCCESS("Monthly reporting workflow queued."))
