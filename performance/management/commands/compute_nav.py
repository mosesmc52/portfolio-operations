import json

from django.core.management.base import BaseCommand, CommandError
from performance.nav import compute_and_save_navsnapshot


class Command(BaseCommand):
    help = "Compute and save NAVSnapshot for a fund (Alpaca)."

    def add_arguments(self, parser):
        parser.add_argument("--fund-id", type=int, required=True)

    def handle(self, *args, **opts):
        try:
            snap = compute_and_save_navsnapshot(fund_id=opts["fund_id"])
        except Exception as e:
            raise CommandError(str(e))

        self.stdout.write(
            json.dumps(
                {
                    "fund_id": opts["fund_id"],
                    "date": str(snap.date),
                    "nav_per_unit": str(snap.nav_per_unit),
                    "aum": str(snap.aum),
                    "total_units": str(snap.total_units),
                },
                indent=2,
            )
        )
