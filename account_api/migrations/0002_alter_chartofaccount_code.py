from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('account_api', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='chartofaccount',
            name='code',
            field=models.CharField(
                blank=True,
                max_length=50,
                null=True,
                unique=True,
            ),
        ),
    ]
