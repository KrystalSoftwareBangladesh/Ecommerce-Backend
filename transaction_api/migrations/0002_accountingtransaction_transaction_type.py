from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transaction_api', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='accountingtransaction',
            name='transaction_type',
            field=models.CharField(
                choices=[
                    ('JOURNAL', 'Journal'),
                    ('PAYMENT', 'Payment'),
                    ('RECEIPT', 'Receipt'),
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
        migrations.AddIndex(
            model_name='accountingtransaction',
            index=models.Index(
                fields=['transaction_type'],
                name='transaction_transac_435d7b_idx',
            ),
        ),
    ]
