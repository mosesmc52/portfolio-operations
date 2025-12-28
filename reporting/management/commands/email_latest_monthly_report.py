from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError
from reporting.tasks import email_latest_monthly_report_to_clients_task


class Command(BaseCommand):
    help = "Email clients the latest monthly report (PDF attached) using django-ses."

    def add_arguments(self, parser):
        parser.add_argument("--fund-id", type=int, required=True)
        parser.add_argument("--from-email", type=str, default=None)
        parser.add_argument("--subject-prefix", type=str, default="")
        parser.add_argument(
            "--include-only-active",
            action="store_true",
            help="Send only to ACTIVE clients",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Do not send; only compute recipients",
        )
        parser.add_argument(
            "--async", dest="run_async", action="store_true", help="Queue via Celery"
        )

    def handle(self, *args, **opts):
        kwargs = {
            "fund_id": opts["fund_id"],
            "from_email": opts["from_email"],
            "subject_prefix": opts["subject_prefix"],
            "include_only_active_clients": bool(opts["include_only_active"]),
            "dry_run": bool(opts["dry_run"]),
        }

        if opts["run_async"]:
            ar = email_latest_monthly_report_to_clients_task.delay(**kwargs)
            self.stdout.write(
                json.dumps({"queued": True, "task_id": ar.id, **kwargs}, indent=2)
            )
            return

        try:
            res = email_latest_monthly_report_to_clients_task.run(**kwargs)
        except Exception as e:
            raise CommandError(str(e))

        self.stdout.write(json.dumps(res, indent=2))
        self.stdout.write(self.style.SUCCESS("Email latest monthly report completed."))
