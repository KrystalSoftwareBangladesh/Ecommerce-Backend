from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('account_api', '0007_alter_chartofaccount_options'),
        ('transaction_api', '0007_alter_accountingtransaction_options'),
        ('sale_api', '0006_alter_sale_options_alter_saleitem_options'),
    ]

    operations = [
        migrations.AddField(
            model_name='sale',
            name='account',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='sales',
                to='account_api.chartofaccount',
            ),
        ),
        migrations.AddField(
            model_name='sale',
            name='accounting_transaction',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='sales',
                to='transaction_api.accountingtransaction',
            ),
        ),
        migrations.AddField(
            model_name='sale',
            name='return_transaction',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='returned_sales',
                to='transaction_api.accountingtransaction',
            ),
        ),
    ]
