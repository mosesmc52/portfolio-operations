"""
WSGI config for operations project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

import sentry_sdk
from configurations.wsgi import get_wsgi_application
from django.conf import settings
from sentry_sdk.integrations.django import DjangoIntegration

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


application = get_wsgi_application()
