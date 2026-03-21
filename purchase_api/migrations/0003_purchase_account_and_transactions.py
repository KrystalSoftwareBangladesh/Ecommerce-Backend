from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('account_api', '0007_alter_chartofaccount_options'),
        ('transaction_api', '0006_alter_accountingtransaction_options_and_more'),
        ('purchase_api', '0002_alter_purchase_options_alter_purchaseitem_options'),
    ]

    operations = [
        migrations.AddField(
            model_name='purchase',
            name='account',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='purchases',
                to='account_api.chartofaccount',
            ),
        ),
        migrations.AddField(
            model_name='purchase',
            name='accounting_transaction',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='purchases',
                to='transaction_api.accountingtransaction',
            ),
        ),
        migrations.AddField(
            model_name='purchase',
            name='cancellation_transaction',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='cancelled_purchases',
                to='transaction_api.accountingtransaction',
            ),
        ),
    ]
