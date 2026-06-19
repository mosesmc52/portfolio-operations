from datetime import date

from accounts.models import AccountBrokerCredential, ClientCapitalAccount
from clients.models import Client
from django.test import TestCase, override_settings
from funds.models import Fund


@override_settings(ACCOUNT_CREDENTIALS_ENCRYPTION_KEY="test-account-credentials-key")
class AccountBrokerCredentialTests(TestCase):
    def test_round_trip_encryption_for_alpaca_credentials(self):
        client = Client.objects.create(full_name="Client One")
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

        credential = AccountBrokerCredential(account=account, broker=Fund.CUSTODIAN_ALPACA)
        credential.set_alpaca_credentials(key_id="AKIA123456", secret_key="secret-xyz")
        credential.full_clean()
        credential.save()

        self.assertNotEqual(credential.alpaca_key_id_encrypted, "AKIA123456")
        self.assertNotEqual(credential.alpaca_secret_key_encrypted, "secret-xyz")
        self.assertEqual(credential.get_alpaca_credentials(), ("AKIA123456", "secret-xyz"))
