from __future__ import annotations

from datetime import date
import json

from django.core.management.base import BaseCommand, CommandError

from performance.services.nav_backfill import (
    backfill_navsnapshots_from_portfolio_history,
)


class Command(BaseCommand):
    help = "Backfill NAVSnapshot rows from stored AccountPortfolioHistory."

    def add_arguments(self, parser):
        parser.add_argument("--fund-id", type=int, required=True)
        parser.add_argument("--start-date", type=str)
        parser.add_argument("--end-date", type=str)

    def handle(self, *args, **opts):
        start_date = None
        end_date = None
        if opts.get("start_date"):
            try:
                start_date = date.fromisoformat(opts["start_date"])
            except ValueError as exc:
                raise CommandError("--start-date must be YYYY-MM-DD.") from exc
        if opts.get("end_date"):
            try:
                end_date = date.fromisoformat(opts["end_date"])
            except ValueError as exc:
                raise CommandError("--end-date must be YYYY-MM-DD.") from exc

        try:
            res = backfill_navsnapshots_from_portfolio_history(
                fund_id=opts["fund_id"],
                start_date=start_date,
                end_date=end_date,
            )
        except Exception as exc:
            raise CommandError(str(exc))

        self.stdout.write(
            json.dumps(
                {
                    "fund_id": res.fund_id,
                    "strategy_code": res.fund_strategy_code,
                    "start_date": str(res.start_date) if res.start_date else None,
                    "end_date": str(res.end_date) if res.end_date else None,
                    "dates_considered": res.dates_considered,
                    "created": res.created,
                    "updated": res.updated,
                    "skipped_no_units": res.skipped_no_units,
                },
                indent=2,
            )
        )
