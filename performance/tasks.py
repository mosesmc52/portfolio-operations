from celery import shared_task
from performance.nav import compute_and_save_navsnapshot


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def compute_navsnapshot_task(self, *, fund_id: int) -> dict:
    snap = compute_and_save_navsnapshot(fund_id=fund_id)
    return {
        "fund_id": fund_id,
        "date": str(snap.date),
        "nav_per_unit": str(snap.nav_per_unit),
        "aum": str(snap.aum),
        "total_units": str(snap.total_units),
    }
