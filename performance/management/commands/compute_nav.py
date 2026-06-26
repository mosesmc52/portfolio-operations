from datetime import date
import json

from django.core.management.base import BaseCommand, CommandError
from funds.models import Fund
from performance.services.nav import compute_and_save_navsnapshot


class Command(BaseCommand):
    help = "Compute and save NAVSnapshot for a fund (Alpaca)."

    def add_arguments(self, parser):
        parser.add_argument("--fund-id", type=int)
        parser.add_argument("--all", dest="run_all", action="store_true")
        parser.add_argument("--date", dest="as_of_date", type=str)

    def handle(self, *args, **opts):
        fund_id = opts.get("fund_id")
        run_all = bool(opts.get("run_all"))
        as_of_raw = opts.get("as_of_date")

        if bool(fund_id) == run_all:
            raise CommandError("Provide exactly one of --fund-id or --all.")

        as_of = None
        if as_of_raw:
            try:
                as_of = date.fromisoformat(as_of_raw)
            except ValueError as exc:
                raise CommandError("--date must be in YYYY-MM-DD format.") from exc

        fund_ids: list[int]
        if run_all:
            fund_ids = list(
                Fund.objects.filter(
                    custodian=Fund.CUSTODIAN_ALPACA,
                    status=Fund.STATUS_ACTIVE,
                )
                .order_by("id")
                .values_list("id", flat=True)
            )
            if not fund_ids:
                raise CommandError("No active Alpaca funds found.")
        else:
            fund_ids = [int(fund_id)]

        payload = []
        for current_fund_id in fund_ids:
            try:
                snap = compute_and_save_navsnapshot(
                    fund_id=current_fund_id,
                    as_of=as_of,
                )
            except Exception as exc:
                raise CommandError(str(exc))

            payload.append(
                {
                    "fund_id": current_fund_id,
                    "date": str(snap.date),
                    "nav_per_unit": str(snap.nav_per_unit),
                    "aum": str(snap.aum),
                    "total_units": str(snap.total_units),
                }
            )

        self.stdout.write(json.dumps(payload if run_all else payload[0], indent=2))
