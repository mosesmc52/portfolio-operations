import os

import sentry_sdk
from celery import Celery
from django.conf import settings
from sentry_sdk.integrations.django import DjangoIntegration

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
os.environ.setdefault("DJANGO_CONFIGURATION", "Development")

import configurations

configurations.setup()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")


dsn = (getattr(settings, "SENTRY_URL", "") or "").strip()
enabled = bool(getattr(settings, "SENTRY_ENABLED", False))

if enabled and dsn:

    sentry_sdk.init(
        dsn=dsn,
        integrations=[DjangoIntegration()],
        send_default_pii=True,
        environment=getattr(settings, "SENTRY_ENVIRONMENT", "development"),
        traces_sample_rate=float(getattr(settings, "SENTRY_TRACES_SAMPLE_RATE", 0.0)),
    )


app = Celery("core")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django apps.
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
