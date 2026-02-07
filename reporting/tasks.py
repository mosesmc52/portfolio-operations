from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

from accounts.models import ClientCapitalAccount
from celery import shared_task
from clients.models import Client
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Sum
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


@dataclass
class EmailSendResult:
    sent: int
    skipped_no_email: int
    skipped_not_invested: int
    skipped_no_report: int
    snapshot_id: int | None = None
    as_of_month: str | None = None


def _get_latest_snapshot_with_report(*, fund_id: int) -> MonthlySnapshot | None:
    """
    Latest MonthlySnapshot for the fund that has a linked MonthlyReportArtifact.
    """
    return (
        MonthlySnapshot.objects.filter(fund_id=fund_id, report_artifact__isnull=False)
        .order_by("-as_of_month")
        .first()
    )


def _split_emails(raw: str) -> list[str]:
    """
    Split on commas/semicolons, trim whitespace, validate, de-dupe.
    """
    if not raw:
        return []

    # support both comma and semicolon separators
    parts = [p.strip() for p in raw.replace(";", ",").split(",")]
    out: list[str] = []
    seen: set[str] = set()

    for p in parts:
        if not p:
            continue
        # Optional: strip common "Name <email@x.com>" formatting if it appears
        if "<" in p and ">" in p:
            p = p[p.find("<") + 1 : p.find(">")].strip()

        try:
            validate_email(p)
        except ValidationError:
            continue  # or log/raise depending on your needs

        key = p.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)

    return out


def _get_recipients_for_fund(*, fund_id: int) -> List[Tuple["Client", str]]:
    """
    Clients who have >0 units in this fund and have at least one valid email.
    Returns a list of (client, email) pairs, splitting comma/semicolon-delimited fields.
    """
    qs = (
        Client.objects.filter(email__isnull=False)
        .exclude(email__exact="")
        .filter(
            clientcapitalaccount__fund_id=fund_id,
            clientcapitalaccount__units__gt=0,
        )
        .distinct()
        .only("id", "email")  # keep it light
    )

    recipients: list[tuple[Client, str]] = []
    for client in qs:
        for email in _split_emails(client.email):
            recipients.append((client, email))

    return recipients


def _subject_for_snapshot(snap: MonthlySnapshot) -> str:
    return f"{snap.fund.strategy_code} Monthly Report — {snap.as_of_month:%Y-%m}"


def _build_body_text(*, snap: MonthlySnapshot, artifact: MonthlyReportArtifact) -> str:
    fund = snap.fund
    lines = [
        f"{fund.strategy_code} Monthly Report",
        f"Period end: {snap.as_of_month:%Y-%m-%d}",
        "",
        "Summary:",
        f"- Fund return: {snap.fund_return:.4%}",
        (
            f"- Benchmark ({snap.benchmark_symbol}) return: {snap.benchmark_return:.4%}"
            if snap.benchmark_return is not None
            else f"- Benchmark ({snap.benchmark_symbol}) return: N/A"
        ),
        (
            f"- Excess return: {snap.excess_return:.4%}"
            if snap.excess_return is not None
            else "- Excess return: N/A"
        ),
        f"- AUM (EOM): ${snap.aum_eom}",
        "",
        "The PDF report is attached.",
        "",
        "Disclosure: For informational purposes only. Past performance is not indicative of future results.",
    ]
    return "\n".join(lines)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def email_latest_monthly_report_to_clients_task(
    self,
    *,
    fund_id: int,
    snapshot_id: int | None = None,
    subject_prefix: str = "",
    from_email: str | None = None,
    include_only_active_clients: bool = True,
    dry_run: bool = False,
) -> dict:
    """
    Email MonthlyReportArtifact (PDF attached) to clients who have units > 0.
    Prefer passing snapshot_id to make it deterministic (best for chained tasks).
    If snapshot_id is None, falls back to latest snapshot with a report for the fund.
    """

    # 1) Pick the snapshot deterministically if provided
    if snapshot_id is not None:
        snap = (
            MonthlySnapshot.objects.select_related("fund")
            .filter(id=snapshot_id, fund_id=fund_id)
            .first()
        )
        if not snap:
            return EmailSendResult(
                sent=0,
                skipped_no_email=0,
                skipped_not_invested=0,
                skipped_no_report=1,
                snapshot_id=snapshot_id,
                as_of_month=None,
            ).__dict__
        # ensure report exists
        if not hasattr(snap, "report_artifact") or snap.report_artifact is None:
            return EmailSendResult(
                sent=0,
                skipped_no_email=0,
                skipped_not_invested=0,
                skipped_no_report=1,
                snapshot_id=snap.id,
                as_of_month=str(snap.as_of_month),
            ).__dict__
    else:
        snap = _get_latest_snapshot_with_report(fund_id=fund_id)
        if not snap:
            return EmailSendResult(
                sent=0,
                skipped_no_email=0,
                skipped_not_invested=0,
                skipped_no_report=1,
                snapshot_id=None,
                as_of_month=None,
            ).__dict__

    artifact: MonthlyReportArtifact | None = getattr(snap, "report_artifact", None)
    if not artifact or not artifact.pdf_file:
        return EmailSendResult(
            sent=0,
            skipped_no_email=0,
            skipped_not_invested=0,
            skipped_no_report=1,
            snapshot_id=snap.id,
            as_of_month=str(snap.as_of_month),
        ).__dict__

    # 2) Determine recipients
    recipients = _get_recipients_for_fund(fund_id=fund_id)

    if include_only_active_clients:
        recipients = [
            c
            for c in recipients
            if getattr(c, "status", None) == getattr(Client, "ACTIVE", "active")
        ]

    # If no recipients, return cleanly
    if not recipients:
        return EmailSendResult(
            sent=0,
            skipped_no_email=0,
            skipped_not_invested=0,
            skipped_no_report=0,
            snapshot_id=snap.id,
            as_of_month=str(snap.as_of_month),
        ).__dict__

    # 3) Read attachment safely (important with FileField)
    artifact.pdf_file.open("rb")
    try:
        pdf_bytes = artifact.pdf_file.read()
    finally:
        artifact.pdf_file.close()

    if not pdf_bytes:
        raise ValueError(
            "Monthly report PDF is empty; pdf_file.read() returned 0 bytes."
        )

    filename = f"{snap.fund.strategy_code}-{snap.as_of_month:%Y-%m}.pdf"

    subject = f"{subject_prefix}{_subject_for_snapshot(snap)}"
    body_text = _build_body_text(snap=snap, artifact=artifact)

    # 4) Resolve sender: prefer explicit argument, then DEFAULT_FROM_EMAIL
    from_email_final = (
        from_email
        or getattr(settings, "DEFAULT_FROM_EMAIL", None)
        or getattr(
            settings, "EMAIL_FROM", None
        )  # backwards compat if you already use EMAIL_FROM
    )
    if not from_email_final:
        raise ValueError("DEFAULT_FROM_EMAIL is not set (or pass from_email=...).")

    sent = 0
    skipped_no_email = 0

    for client in recipients:
        email = (getattr(client, "email", None) or "").strip()
        if not email:
            skipped_no_email += 1
            continue

        if dry_run:
            continue

        msg = EmailMessage(
            subject=subject,
            body=body_text,
            from_email=from_email_final,
            to=[email],
        )
        msg.attach(filename, pdf_bytes, "application/pdf")
        msg.send(fail_silently=False)
        sent += 1

    return EmailSendResult(
        sent=sent,
        skipped_no_email=skipped_no_email,
        skipped_not_invested=0,
        skipped_no_report=0,
        snapshot_id=snap.id,
        as_of_month=str(snap.as_of_month),
    ).__dict__
