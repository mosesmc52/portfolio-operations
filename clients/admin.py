# clients/admin.py
from django.contrib import admin

from .models import Client


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("full_name", "client_type", "status", "email", "created_at")
    list_filter = ("client_type", "status")
    search_fields = ("full_name", "email")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)
