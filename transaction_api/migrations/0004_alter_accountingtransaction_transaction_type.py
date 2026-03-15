from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transaction_api', '0003_accountingtransaction_transaction_datetime'),
    ]

    operations = [
        migrations.AlterField(
            model_name='accountingtransaction',
            name='transaction_type',
            field=models.CharField(
                choices=[
                    ('JOURNAL', 'Journal'),
                    ('PAYMENT', 'Payment'),
                    ('RECEIPT', 'Receipt'),
                    ('INVESTMENT', 'Investment'),
                    ('PURCHASE', 'Purchase'),
                    ('SALE', 'Sale'),
                    ('ADJUSTMENT', 'Adjustment'),
                    ('OPENING_BALANCE', 'Opening Balance'),
                    ('TRANSFER', 'Transfer'),
                ],
                default='JOURNAL',
                max_length=30,
            ),
        ),
    ]
