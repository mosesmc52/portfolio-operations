from accounts.models import AccountBrokerCredential
from rest_framework import serializers


class ActiveCredentialSerializer(serializers.ModelSerializer):
    account_id = serializers.IntegerField(source="account.id", read_only=True)
    client_id = serializers.IntegerField(source="account.client.id", read_only=True)
    client_name = serializers.CharField(source="account.client.full_name", read_only=True)
    fund_id = serializers.IntegerField(source="account.fund.id", read_only=True)
    fund_strategy_code = serializers.CharField(
        source="account.fund.strategy_code", read_only=True
    )
    masked_key_id = serializers.CharField(read_only=True)

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
