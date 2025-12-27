from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError
from reporting.tasks import generate_monthly_report_artifact_task


class Command(BaseCommand):
    help = "Generate MonthlyReportArtifact for a given MonthlySnapshot."

    def add_arguments(self, parser):
        parser.add_argument("--snapshot-id", type=int, required=True)
        parser.add_argument("--async", dest="run_async", action="store_true")

    def handle(self, *args, **opts):
        kwargs = {"snapshot_id": opts["snapshot_id"]}

        if opts["run_async"]:
            ar = generate_monthly_report_artifact_task.delay(**kwargs)
            self.stdout.write(
                json.dumps({"queued": True, "task_id": ar.id, **kwargs}, indent=2)
            )
            return

        try:
            res = generate_monthly_report_artifact_task.run(**kwargs)
        except Exception as e:
            raise CommandError(str(e))

        self.stdout.write(json.dumps(res, indent=2))
        self.stdout.write(self.style.SUCCESS("MonthlyReport generated successfully."))
