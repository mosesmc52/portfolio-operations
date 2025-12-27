from __future__ import annotations

from celery import shared_task
from django.core.files.base import ContentFile
from django.db import transaction
from performance.models import MonthlySnapshot
from reporting.models import MonthlyReportArtifact
from reporting.services.monthly_reporting_service import MonthlyReportingService


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def generate_monthly_report_artifact_task(
    self,
    *,
    snapshot_id: int,
) -> dict:
    """
    Generate/upsert MonthlyReportArtifact for a given MonthlySnapshot.
    """
    snap = MonthlySnapshot.objects.select_related("fund").get(id=snapshot_id)
    fund = snap.fund

    # Derive year/month from as_of_month
    year = snap.as_of_month.year
    month = snap.as_of_month.month

    svc = MonthlyReportingService()
    report = svc.generate_monthly_report(fund_id=fund.id, year=year, month=month)

    base = f"{fund.strategy_code}-{year}-{month:02d}"

    with transaction.atomic():
        artifact, _ = MonthlyReportArtifact.objects.update_or_create(
            snapshot=snap,
            defaults={"commentary": report.commentary},
        )
        artifact.html_file.save(
            f"{base}.html", ContentFile(report.html.encode("utf-8")), save=False
        )
        artifact.pdf_file.save(f"{base}.pdf", ContentFile(report.pdf_bytes), save=False)
        artifact.chart_file.save(
            f"{base}-forecast.png", ContentFile(report.forecast_chart_png), save=False
        )
        artifact.save()

    return {
        "artifact_id": artifact.id,
        "snapshot_id": snap.id,
        "fund_id": fund.id,
        "as_of_month": str(snap.as_of_month),
    }
