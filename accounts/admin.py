# apps/accounts/admin.py
from __future__ import annotations

from decimal import Decimal

from accounts.models import AccountBrokerCredential, CapitalFlow, ClientCapitalAccount
from accounts.services.capital_flows import apply_capital_flow
from accounts.utils.external_refs import generate_external_ref
from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest
from performance.models import NAVSnapshot

INCEPTION_NAV = Decimal("1.0")  # choose 1.0 or 100.0, but be consistent


class ClientCapitalAccountInline(admin.TabularInline):
    model = ClientCapitalAccount
    extra = 0
    fields = ("fund", "units", "nav_per_unit", "last_valuation_date")
    ordering = ("fund",)


class AccountBrokerCredentialForm(forms.ModelForm):
    alpaca_key_id_input = forms.CharField(
        label="Alpaca key ID",
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Leave blank to keep the currently stored key ID.",
    )
    alpaca_secret_key_input = forms.CharField(
        label="Alpaca secret key",
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Leave blank to keep the currently stored secret key.",
    )

    class Meta:
        model = AccountBrokerCredential
        fields = ("account", "broker", "environment", "is_active")

    def clean(self):
        cleaned_data = super().clean()
        key_id = cleaned_data.get("alpaca_key_id_input")
        secret_key = cleaned_data.get("alpaca_secret_key_input")

        if self.instance.pk is None and (not key_id or not secret_key):
            raise ValidationError("Both Alpaca key ID and Alpaca secret key are required.")

        if bool(key_id) != bool(secret_key):
            raise ValidationError(
                "Provide both Alpaca key ID and Alpaca secret key together when rotating credentials."
            )

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        key_id = self.cleaned_data.get("alpaca_key_id_input")
        secret_key = self.cleaned_data.get("alpaca_secret_key_input")
        if key_id and secret_key:
            instance.set_alpaca_credentials(key_id=key_id, secret_key=secret_key)
        if commit:
            instance.save()
        return instance


class CapitalFlowInline(admin.TabularInline):
    model = CapitalFlow
    extra = 0
    fields = (
        "flow_date",
        "fund",
        "flow_type",
        "amount",
        "nav_at_flow",
        "units_delta",
        "external_ref",
    )
    ordering = ("-flow_date",)


@admin.register(ClientCapitalAccount)
class ClientCapitalAccountAdmin(admin.ModelAdmin):
    list_display = (
        "client",
        "fund",
        "fund_strategy",
        "units",
        "nav_per_unit",
        "equity_estimate",
        "last_valuation_date",
    )
    list_filter = ("fund",)
    search_fields = (
        "client__name",
        "client__email",
        "fund__strategy_code",
        "fund__name",
    )

    def fund_strategy(self, obj):
        return getattr(obj.fund, "strategy_code", "")

    fund_strategy.short_description = "Strategy"

    def equity_estimate(self, obj):
        if obj.units is None or obj.nav_per_unit is None:
            return "-"
        return float(obj.units) * float(obj.nav_per_unit)

    equity_estimate.short_description = "Equity (est.)"


@admin.register(AccountBrokerCredential)
class AccountBrokerCredentialAdmin(admin.ModelAdmin):
    form = AccountBrokerCredentialForm
    list_display = (
        "account",
        "broker",
        "environment",
        "masked_key_id_display",
        "is_active",
        "updated_at",
    )
    list_filter = ("broker", "environment", "is_active")
    search_fields = (
        "account__client__full_name",
        "account__client__email",
        "account__fund__strategy_code",
        "account__fund__name",
    )
    readonly_fields = ("masked_key_id_display", "created_at", "updated_at")
    fields = (
        "account",
        "broker",
        "environment",
        "masked_key_id_display",
        "alpaca_key_id_input",
        "alpaca_secret_key_input",
        "is_active",
        "created_at",
        "updated_at",
    )

    def masked_key_id_display(self, obj):
        if not obj.pk:
            return ""
        return obj.masked_key_id

    masked_key_id_display.short_description = "Stored key ID"


@admin.register(CapitalFlow)
class CapitalFlowAdmin(admin.ModelAdmin):
    """
    CapitalFlow admin:
    - external_ref is auto-generated
    - nav_at_flow and units_delta are computed
    - ledger entries are immutable
    """

    list_display = (
        "flow_date",
        "client",
        "fund",
        "flow_type",
        "amount",
        "nav_at_flow",
        "units_delta",
        "external_ref",
        "created_at",
    )

    list_filter = ("fund", "flow_type")
    search_fields = (
        "client__name",
        "client__email",
        "fund__strategy_code",
        "external_ref",
    )
    date_hierarchy = "flow_date"

    # external_ref is READ-ONLY
    readonly_fields = ("external_ref", "nav_at_flow", "units_delta", "created_at")

    # Do NOT include external_ref as an editable input
    fields = (
        "client",
        "fund",
        "flow_type",
        "flow_date",
        "amount",
        "external_ref",
        "nav_at_flow",
        "units_delta",
        "created_at",
    )

    def save_model(
        self, request: HttpRequest, obj: CapitalFlow, form, change: bool
    ) -> None:
        if change:
            raise ValidationError(
                "Capital flows are immutable. Create an offsetting flow to correct mistakes."
            )

        with transaction.atomic():
            # ----------------------------
            # Ensure inception NAV exists if needed
            # ----------------------------
            if not NAVSnapshot.objects.filter(
                fund=obj.fund, date=obj.flow_date
            ).exists():
                has_any_nav = NAVSnapshot.objects.filter(fund=obj.fund).exists()
                has_any_flow = CapitalFlow.objects.filter(fund=obj.fund).exists()

                if not has_any_nav and not has_any_flow:
                    NAVSnapshot.objects.create(
                        fund=obj.fund,
                        date=obj.flow_date,
                        nav_per_unit=1.0,
                        total_units=0,
                        aum=0,
                    )

            # ----------------------------
            # Auto-generate external_ref
            # ----------------------------
            base_ref = generate_external_ref(
                client_id=obj.client.id,
                fund_strategy=obj.fund.strategy_code,
                flow_date=obj.flow_date,
            )

            # Ensure uniqueness (same client/fund/date may have multiple flows)
            seq = 1
            external_ref = f"{base_ref}-{seq:03d}"
            while CapitalFlow.objects.filter(
                fund=obj.fund,
                client=obj.client,
                external_ref=external_ref,
            ).exists():
                seq += 1
                external_ref = f"{base_ref}-{seq:03d}"

            # ----------------------------
            # Apply flow via service
            # ----------------------------
            flow = apply_capital_flow(
                client=obj.client,
                fund=obj.fund,
                flow_type=obj.flow_type,
                flow_date=obj.flow_date,
                amount=obj.amount,
                external_ref=external_ref,
            )

        # Important: link admin object to created row
        obj.pk = flow.pk

        messages.success(
            request,
            f"Capital flow created. external_ref={flow.external_ref} "
            f"nav_at_flow={flow.nav_at_flow} units_delta={flow.units_delta}",
        )

    def has_change_permission(self, request, obj=None) -> bool:
        # View-only once created
        if obj is not None and request.method in ("POST", "PUT", "PATCH"):
            return False
        return super().has_change_permission(request, obj=obj)
