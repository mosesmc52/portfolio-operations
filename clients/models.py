# clients/models.py
from django.db import models
from django.utils import timezone


class Client(models.Model):
    INDIVIDUAL = "individual"
    ENTITY = "entity"
    CLIENT_TYPE_CHOICES = [
        (INDIVIDUAL, "Individual"),
        (ENTITY, "Entity"),
    ]

    PROSPECT = "prospect"
    ACTIVE = "active"
    TERMINATED = "terminated"
    STATUS_CHOICES = [
        (PROSPECT, "Prospect"),
        (ACTIVE, "Active"),
        (TERMINATED, "Terminated"),
    ]

    full_name = models.CharField(max_length=200)
    client_type = models.CharField(
        max_length=20, choices=CLIENT_TYPE_CHOICES, default=INDIVIDUAL
    )

    email = models.EmailField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PROSPECT)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.full_name} ({self.status})"
