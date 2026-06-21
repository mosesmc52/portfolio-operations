from accounts.models import AccountBrokerCredential
from django.core.exceptions import ImproperlyConfigured, ValidationError
from rest_framework import serializers


class ActiveCredentialSerializer(serializers.ModelSerializer):
    account_id = serializers.IntegerField(source="account.id", read_only=True)
    client_id = serializers.IntegerField(source="account.client.id", read_only=True)
    client_name = serializers.CharField(source="account.client.full_name", read_only=True)
    fund_id = serializers.IntegerField(source="account.fund.id", read_only=True)
    fund_strategy_code = serializers.CharField(
        source="account.fund.strategy_code", read_only=True
    )
    key_id = serializers.SerializerMethodField()
    secret_key = serializers.SerializerMethodField()
    masked_key_id = serializers.CharField(read_only=True)

    def _get_alpaca_value(self, obj: AccountBrokerCredential, index: int) -> str:
        try:
            credentials = obj.get_alpaca_credentials()
        except (ValidationError, ImproperlyConfigured):
            return ""
        return credentials[index]

    def get_key_id(self, obj: AccountBrokerCredential) -> str:
        return self._get_alpaca_value(obj, 0)

    def get_secret_key(self, obj: AccountBrokerCredential) -> str:
        return self._get_alpaca_value(obj, 1)

    class Meta:
        model = AccountBrokerCredential
        fields = (
            "id",
            "account_id",
            "client_id",
            "client_name",
            "fund_id",
            "fund_strategy_code",
            "broker",
            "environment",
            "key_id",
            "secret_key",
            "masked_key_id",
            "is_active",
            "created_at",
            "updated_at",
        )


class RevealSecretRequestSerializer(serializers.Serializer):
    key_id = serializers.CharField(max_length=256, trim_whitespace=True)


class RevealSecretResponseSerializer(serializers.Serializer):
    credential_id = serializers.IntegerField()
    account_id = serializers.IntegerField()
    client_name = serializers.CharField()
    fund_strategy_code = serializers.CharField()
    broker = serializers.CharField()
    key_id = serializers.CharField()
    secret_key = serializers.CharField()
