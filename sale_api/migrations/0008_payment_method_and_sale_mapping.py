from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('account_api', '0007_alter_chartofaccount_options'),
        ('sale_api', '0007_sale_account_and_transactions'),
    ]

    operations = [
        migrations.CreateModel(
            name='PaymentMethod',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True, db_index=True)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                (
                    'deleted_at',
                    models.DateTimeField(blank=True, db_index=True, null=True),
                ),
                ('code', models.CharField(max_length=50, unique=True)),
                ('name', models.CharField(max_length=100)),
                ('description', models.TextField(blank=True, null=True)),
                ('allow_account_override', models.BooleanField(default=False)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                (
                    'created_by',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='paymentmethod_created',
                        to='user_api.user',
                    ),
                ),
                (
                    'updated_by',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='paymentmethod_updated',
                        to='user_api.user',
                    ),
                ),
                (
                    'default_account',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='payment_methods',
                        to='account_api.chartofaccount',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Payment Method',
                'verbose_name_plural': 'Payment Methods',
                'ordering': ['sort_order', 'name', 'id'],
            },
        ),
        migrations.AddField(
            model_name='sale',
            name='payment_method',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='sales',
                to='sale_api.paymentmethod',
            ),
        ),
        migrations.AddIndex(
            model_name='paymentmethod',
            index=models.Index(fields=['code'], name='sale_api_pa_code_3ef515_idx'),
        ),
        migrations.AddIndex(
            model_name='paymentmethod',
            index=models.Index(fields=['name'], name='sale_api_pa_name_7786a7_idx'),
        ),
        migrations.AddIndex(
            model_name='paymentmethod',
            index=models.Index(
                fields=['sort_order'],
                name='sale_api_pa_sort_or_7388df_idx',
            ),
        ),
    ]
