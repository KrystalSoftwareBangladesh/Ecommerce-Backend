from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transaction_api', '0004_alter_accountingtransaction_transaction_type'),
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
                    ('OWNER_WITHDRAWAL', 'Owner Withdrawal'),
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
