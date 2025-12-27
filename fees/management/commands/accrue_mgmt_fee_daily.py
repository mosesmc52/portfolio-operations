from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from fees.services.fees import accrue_management_fee_for_day
from funds.models import Fund


class Command(BaseCommand):
    help = (
        "Accrue daily management fee for a fund based on AUM "
        "using NAVSnapshot for the given date."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--fund-id",
            type=int,
            required=True,
            help="Fund ID to accrue management fee for",
        )
        parser.add_argument(
            "--annual-rate",
            type=str,
            required=True,
            help="Annual management fee rate (e.g. 0.02 for 2%)",
        )
        parser.add_argument(
            "--date",
            type=str,
            default=None,
            help="Valuation date YYYY-MM-DD (default: today)",
        )

    def handle(self, *args, **opts):
        fund_id = opts["fund_id"]
        annual_rate = Decimal(opts["annual_rate"])
        date_str = opts.get("date")

        if annual_rate <= 0:
            raise CommandError("annual-rate must be > 0")

        try:
            fund = Fund.objects.get(id=fund_id)
        except Fund.DoesNotExist:
            raise CommandError(f"Fund not found: id={fund_id}")

        if date_str:
            try:
                as_of = date.fromisoformat(date_str)
            except ValueError:
                raise CommandError("Invalid --date format. Use YYYY-MM-DD")
        else:
            as_of = timezone.now().date()

        try:
            fee = accrue_management_fee_for_day(
                fund=fund,
                as_of=as_of,
                annual_rate=annual_rate,
            )
        except Exception as e:
            raise CommandError(str(e))

        payload = {
            "fund_id": fund.id,
            "strategy_code": fund.strategy_code,
            "date": str(as_of),
            "annual_rate": str(annual_rate),
            "daily_fee": str(fee.amount),
            "expense_type": fee.expense_type,
            "is_paid": fee.is_paid,
        }

        self.stdout.write(json.dumps(payload, indent=2))
