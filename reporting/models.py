# reporting/models.py
from django.db import models
from django.utils import timezone


class MonthlyReportArtifact(models.Model):
    snapshot = models.OneToOneField(
        "performance.MonthlySnapshot",
        on_delete=models.CASCADE,
        related_name="report_artifact",
    )

    # LLM-generated commentary
    commentary = models.TextField(
        blank=True,
        null=True,
        help_text="LLM-generated monthly commentary (Markdown)",
    )

    # Generated artifacts
    html_file = models.FileField(
        upload_to="reports/monthly/html/",
        null=True,
        blank=True,
    )
    pdf_file = models.FileField(
        upload_to="reports/monthly/pdf/",
        null=True,
        blank=True,
    )
    chart_file = models.FileField(
        upload_to="reports/monthly/charts/",
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        snap = self.snapshot
        return f"{snap.fund.strategy_code} {snap.as_of_month:%Y-%m}"
