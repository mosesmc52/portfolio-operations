from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError
from performance.tasks import generate_monthly_snapshot_task


class Command(BaseCommand):
    help = "Generate MonthlySnapshot (canonical metrics) for a fund/month."

    def add_arguments(self, parser):
        parser.add_argument("--fund-id", type=int, required=True)
        parser.add_argument("--year", type=int, required=True)
        parser.add_argument("--month", type=int, required=True)
        parser.add_argument("--benchmark", type=str, default="SPY")
        parser.add_argument("--strategy-version", type=str, default=None)
        parser.add_argument("--model-change", action="store_true")

        parser.add_argument("--async", dest="run_async", action="store_true")

    def handle(self, *args, **opts):
        kwargs = {
            "fund_id": opts["fund_id"],
            "year": opts["year"],
            "month": opts["month"],
            "benchmark_symbol": opts["benchmark"],
            "strategy_version": opts["strategy_version"],
            "model_change": bool(opts["model_change"]),
        }

        if opts["run_async"]:
            ar = generate_monthly_snapshot_task.delay(**kwargs)
            self.stdout.write(
                json.dumps({"queued": True, "task_id": ar.id, **kwargs}, indent=2)
            )
            return

        try:
            res = generate_monthly_snapshot_task.run(**kwargs)
        except Exception as e:
            raise CommandError(str(e))

        self.stdout.write(json.dumps(res, indent=2))
        self.stdout.write(self.style.SUCCESS("MonthlySnapshot generated successfully."))
