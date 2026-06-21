from datetime import date

from accounts.models import AccountBrokerCredential, ClientCapitalAccount
from clients.models import Client
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from funds.models import Fund
from rest_framework.test import APIClient


@override_settings(ACCOUNT_CREDENTIALS_ENCRYPTION_KEY="test-account-credentials-key")
class ActiveCredentialApiTests(TestCase):
    def setUp(self):
        self.api_client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="api-user",
            password="test-pass-123",
        )

        client = Client.objects.create(full_name="Client One", status=Client.ACTIVE)
        fund = Fund.objects.create(
            name="Alpaca Fund",
            strategy_code="ALPACA_FUND",
            inception_date=date(2026, 1, 1),
            custodian=Fund.CUSTODIAN_ALPACA,
            custodian_account_id="acct-1",
        )
        account = ClientCapitalAccount.objects.create(
            client=client,
            fund=fund,
            units="10.0",
            nav_per_unit="1.25",
            last_valuation_date=date(2026, 1, 31),
        )

        active_credential = AccountBrokerCredential(
            account=account,
            broker=Fund.CUSTODIAN_ALPACA,
            environment=AccountBrokerCredential.ENVIRONMENT_LIVE,
            is_active=True,
        )
        active_credential.set_alpaca_credentials(
            key_id="AKIA123456",
            secret_key="secret-xyz",
        )
        active_credential.full_clean()
        active_credential.save()

        token_response = self.api_client.post(
            "/api/token/",
            {"username": "api-user", "password": "test-pass-123"},
            format="json",
        )
        self.access_token = token_response.json()["access"]

    def test_requires_authentication(self):
        response = self.api_client.get("/api/credentials/active/")
        self.assertEqual(response.status_code, 401)

    def test_returns_active_credentials_for_authenticated_user(self):
        self.api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access_token}")

        response = self.api_client.get("/api/credentials/active/")
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["client_name"], "Client One")
        self.assertEqual(payload[0]["fund_strategy_code"], "ALPACA_FUND")
        self.assertEqual(payload[0]["environment"], AccountBrokerCredential.ENVIRONMENT_LIVE)
        self.assertEqual(payload[0]["key_id"], "AKIA123456")
        self.assertEqual(payload[0]["secret_key"], "secret-xyz")
        self.assertTrue(payload[0]["masked_key_id"].startswith("AKIA"))
        self.assertNotIn("alpaca_secret_key_encrypted", payload[0])

    def test_reveals_secret_for_matching_active_key_id(self):
        self.api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access_token}")

        response = self.api_client.post(
            "/api/credentials/reveal-secret/",
            {"key_id": "AKIA123456"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["key_id"], "AKIA123456")
        self.assertEqual(payload["secret_key"], "secret-xyz")
        self.assertEqual(payload["client_name"], "Client One")
        self.assertEqual(payload["fund_strategy_code"], "ALPACA_FUND")

    def test_reveal_secret_returns_not_found_for_unknown_key_id(self):
        self.api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access_token}")

        response = self.api_client.post(
            "/api/credentials/reveal-secret/",
            {"key_id": "UNKNOWN-KEY"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
