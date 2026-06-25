from __future__ import annotations

from celery import shared_task

from accounts.services.portfolio_history import sync_alpaca_account_portfolio_history


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def sync_alpaca_account_portfolio_history_task(
    self,
    *,
    fund_id: int | None = None,
    account_id: int | None = None,
    period: str = "1A",
) -> dict:
    res = sync_alpaca_account_portfolio_history(
        fund_id=fund_id,
        account_id=account_id,
        period=period,
    )
    return {
        "fund_id": fund_id,
        "account_id": account_id,
        "period": period,
        "accounts_processed": res.accounts_processed,
        "points_fetched": res.points_fetched,
        "created": res.created,
        "updated": res.updated,
    }
