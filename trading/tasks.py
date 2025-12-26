from __future__ import annotations

from celery import shared_task
from trading.sync import sync_alpaca_filled_orders_last_days


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def sync_alpaca_filled_orders_last_days_task(
    self, *, fund_id: int, days: int = 7, limit: int = 500
) -> dict:
    """
    Celery wrapper for syncing filled orders from Alpaca.
    """
    res = sync_alpaca_filled_orders_last_days(fund_id=fund_id, days=days, limit=limit)
    return {
        "fund_id": res.fund_id,
        "strategy_code": res.fund_strategy_code,
        "days": res.days,
        "fetched": res.fetched,
        "created": res.created,
        "updated": res.updated,
    }
