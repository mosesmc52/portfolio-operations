from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from accounts.tasks import sync_alpaca_account_portfolio_history_task


class Command(BaseCommand):
    help = "Sync daily Alpaca portfolio history for all accounts, one fund, or one client capital account."

    def add_arguments(self, parser):
        parser.add_argument("--fund-id", type=int)
        parser.add_argument("--account-id", type=int)
        parser.add_argument("--all", dest="sync_all", action="store_true")
        parser.add_argument("--period", type=str, default="1A")
        parser.add_argument("--async", dest="run_async", action="store_true")

    def handle(self, *args, **opts):
        fund_id = opts.get("fund_id")
        account_id = opts.get("account_id")
        sync_all = bool(opts.get("sync_all"))
        period = opts["period"]

        scope_count = int(bool(fund_id)) + int(bool(account_id)) + int(sync_all)
        if scope_count != 1:
            raise CommandError("Provide exactly one of --all, --fund-id, or --account-id.")

        kwargs = {
            "fund_id": None if sync_all else fund_id,
            "account_id": None if sync_all else account_id,
            "period": period,
        }

        if opts["run_async"]:
            ar = sync_alpaca_account_portfolio_history_task.delay(**kwargs)
            self.stdout.write(json.dumps({"queued": True, "task_id": ar.id, **kwargs}, indent=2))
            return

        try:
            res = sync_alpaca_account_portfolio_history_task.run(**kwargs)
        except Exception as exc:
            raise CommandError(str(exc))

        self.stdout.write(json.dumps(res, indent=2))
        self.stdout.write(self.style.SUCCESS("Alpaca account portfolio history synced."))
