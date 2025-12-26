from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError
from trading.sync import sync_alpaca_filled_orders_last_days


class Command(BaseCommand):
    help = "Sync Alpaca filled orders from the last X days into TradeFill (one row per filled order)."

    def add_arguments(self, parser):
        parser.add_argument("--fund-id", type=int, required=True)
        parser.add_argument("--days", type=int, default=7)
        parser.add_argument("--limit", type=int, default=500)

    def handle(self, *args, **opts):
        fund_id = int(opts["fund_id"])
        days = int(opts["days"])
        limit = int(opts["limit"])

        try:
            res = sync_alpaca_filled_orders_last_days(
                fund_id=fund_id, days=days, limit=limit
            )
        except Exception as e:
            raise CommandError(str(e))

        payload = {
            "fund_id": res.fund_id,
            "strategy_code": res.fund_strategy_code,
            "days": res.days,
            "fetched": res.fetched,
            "created": res.created,
            "updated": res.updated,
        }
        self.stdout.write(json.dumps(payload, indent=2))
