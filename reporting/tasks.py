from __future__ import annotations

from dataclasses import dataclass
from html import escape
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


def _get_recipients_for_fund(
    *,
    fund_id: int,
    include_only_active_clients: bool = True,
) -> list[tuple[str, str]]:
    """
    Clients who have >0 units in this fund and have at least one valid email.
    Returns a de-duplicated list of valid email addresses, splitting
    comma/semicolon-delimited fields.
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

    if include_only_active_clients:
        qs = qs.filter(status=getattr(Client, "ACTIVE", "active"))

    recipients: list[tuple[str, str]] = []
    seen: set[str] = set()
    for client in qs:
        for email in _split_emails(client.email):
            key = email.lower()
            if key in seen:
                continue
            seen.add(key)
            recipients.append((email, client.full_name))

    return recipients


def _personalize_report_html(*, html_text: str, client_full_name: str) -> str:
    return html_text.replace("Client Copy", escape(client_full_name))


def _render_pdf_from_html(*, html_text: str) -> bytes:
    try:
        from weasyprint import HTML
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "WeasyPrint is required for personalized PDF generation during email send."
        ) from exc
    return HTML(string=html_text).write_pdf()


def _subject_for_snapshot(snap: MonthlySnapshot) -> str:
    return f"{snap.fund.strategy_code} Weekly Report — {snap.as_of_month:%Y-%m}"


def _build_body_text(*, snap: MonthlySnapshot, artifact: MonthlyReportArtifact) -> str:
    lines = [
        "The PDF report is attached.",
        "",
        "Disclosure: Past performance is not indicative of future results.",
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
    recipients = _get_recipients_for_fund(
        fund_id=fund_id,
        include_only_active_clients=include_only_active_clients,
    )

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

    html_text: str | None = None
    if artifact.html_file:
        artifact.html_file.open("rb")
        try:
            html_text = artifact.html_file.read().decode("utf-8")
        finally:
            artifact.html_file.close()

    # 3) Read generic attachment safely as fallback
    artifact.pdf_file.open("rb")
    try:
        generic_pdf_bytes = artifact.pdf_file.read()
    finally:
        artifact.pdf_file.close()

    if not generic_pdf_bytes:
        raise ValueError(
            "Weekly report PDF is empty; pdf_file.read() returned 0 bytes."
        )

    filename = f"adaptive-multi-strategy-update-{snap.as_of_month:%m-%d-%Y}.pdf"

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

    for email, client_full_name in recipients:
        email = (email or "").strip()
        if not email:
            skipped_no_email += 1
            continue

        if dry_run:
            continue

        pdf_bytes = generic_pdf_bytes
        if html_text:
            personalized_html = _personalize_report_html(
                html_text=html_text,
                client_full_name=client_full_name,
            )
            pdf_bytes = _render_pdf_from_html(html_text=personalized_html)

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
