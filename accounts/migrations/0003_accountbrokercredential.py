from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_remove_capitalflow_accounts_ca_fund_id_f5a939_idx_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="AccountBrokerCredential",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "broker",
                    models.CharField(
                        choices=[("ALPACA", "Alpaca"), ("IBKR", "Interactive Brokers")],
                        default="ALPACA",
                        max_length=16,
                    ),
                ),
                ("alpaca_key_id_encrypted", models.TextField(blank=True, default="")),
                ("alpaca_secret_key_encrypted", models.TextField(blank=True, default="")),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "account",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="broker_credential",
                        to="accounts.clientcapitalaccount",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["broker", "is_active"],
                        name="accounts_ac_broker_4df8fa_idx",
                    ),
                ],
            },
        ),
    ]
