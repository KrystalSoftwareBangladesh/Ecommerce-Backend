from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("sale_api", "0014_sale_shipping_method_snapshot"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="sale",
            options={
                "permissions": [
                    (
                        "collect_sale_payment",
                        "Can collect sale payment",
                    ),
                ],
                "verbose_name": "Sale",
                "verbose_name_plural": "Sales",
            },
        ),
    ]
