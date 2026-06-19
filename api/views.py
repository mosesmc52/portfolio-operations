from accounts.models import AccountBrokerCredential
from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import (
    ActiveCredentialSerializer,
    RevealSecretRequestSerializer,
    RevealSecretResponseSerializer,
)


class ActiveCredentialListView(ListAPIView):
    serializer_class = ActiveCredentialSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            AccountBrokerCredential.objects.filter(is_active=True)
            .select_related("account__client", "account__fund")
            .order_by("account__client__full_name", "account__fund__strategy_code")
        )


class RevealCredentialSecretView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request_serializer = RevealSecretRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)

        key_id = request_serializer.validated_data["key_id"]

        for credential in (
            AccountBrokerCredential.objects.filter(is_active=True)
            .select_related("account__client", "account__fund")
            .order_by("id")
        ):
            try:
                stored_key_id, stored_secret_key = credential.get_alpaca_credentials()
            except ValidationError:
                continue

            if stored_key_id != key_id:
                continue

            response_serializer = RevealSecretResponseSerializer(
                {
                    "credential_id": credential.id,
                    "account_id": credential.account_id,
                    "client_name": credential.account.client.full_name,
                    "fund_strategy_code": credential.account.fund.strategy_code,
                    "broker": credential.broker,
                    "key_id": stored_key_id,
                    "secret_key": stored_secret_key,
                }
            )
            return Response(response_serializer.data, status=status.HTTP_200_OK)

        return Response(
            {"detail": "No active credential found for the provided key ID."},
            status=status.HTTP_404_NOT_FOUND,
        )
