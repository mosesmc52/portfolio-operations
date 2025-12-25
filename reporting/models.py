# reporting/models.py
from django.db import models
from django.utils import timezone
from performance.models import MonthlySnapshot


class Report(models.Model):
    snapshot = models.OneToOneField(
        MonthlySnapshot, on_delete=models.CASCADE, related_name="report"
    )

    tearsheet_pdf_path = models.CharField(
        max_length=255, help_text="Path to generated tear sheet PDF"
    )

    commentary_md_path = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Path to AI-generated commentary (Markdown)",
    )

    commentary_pdf_path = models.CharField(max_length=255, blank=True, null=True)

    llm_model = models.CharField(max_length=64, blank=True, null=True)

    prompt_hash = models.CharField(max_length=64, blank=True, null=True)

    inputs_hash = models.CharField(max_length=64, blank=True, null=True)

    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Report | {self.snapshot}"
