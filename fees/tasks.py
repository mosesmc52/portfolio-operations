from decimal import Decimal

from celery import shared_task
from django.utils import timezone
from fees.services.fees import accrue_management_fee_for_day
from funds.models import Fund


@shared_task
def accrue_mgmt_fee_daily_task(*, fund_id: int, annual_rate: str = "0.02") -> dict:
    fund = Fund.objects.get(id=fund_id)
    as_of = timezone.now().date()
    fee = accrue_management_fee_for_day(
        fund=fund, as_of=as_of, annual_rate=Decimal(annual_rate)
    )
    return {"fund_id": fund_id, "date": str(as_of), "fee": str(fee.amount)}
