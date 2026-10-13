# Generated for storefront shipping method snapshots.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sale_api", "0013_sale_request_fingerprint_alter_sale_idempotency_key"),
    ]

    operations = [
        migrations.AddField(
            model_name="sale",
            name="shipping_method_snapshot",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Snapshot of the selected shipping method "
                    "at order placement."
                ),
            ),
        ),
    ]
