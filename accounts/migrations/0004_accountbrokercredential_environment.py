from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_accountbrokercredential"),
    ]

    operations = [
        migrations.AddField(
            model_name="accountbrokercredential",
            name="environment",
            field=models.CharField(
                choices=[("paper", "Paper"), ("live", "Live")],
                default="paper",
                max_length=16,
            ),
        ),
    ]
