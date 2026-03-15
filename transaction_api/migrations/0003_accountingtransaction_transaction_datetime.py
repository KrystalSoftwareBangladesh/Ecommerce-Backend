from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transaction_api', '0002_accountingtransaction_transaction_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='accountingtransaction',
            name='transaction_datetime',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name='accountingtransaction',
            index=models.Index(
                fields=['transaction_datetime'],
                name='transaction_transac_7e9ab8_idx',
            ),
        ),
    ]
