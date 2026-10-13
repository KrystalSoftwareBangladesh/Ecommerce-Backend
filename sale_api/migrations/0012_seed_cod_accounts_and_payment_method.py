# sale_api/migrations/0012_seed_cod_accounts_and_payment_method.py
"""
Seed the accounting infrastructure required for
storefront COD orders.

Creates (idempotently):
- Accounts Receivable (ASSET)
- Shipping Revenue (REVENUE)
- Cash on Delivery PaymentMethod linked to a
  Cash/Bank ASSET account

This migration is safe for existing deployments
and repeated execution. It inspects for existing
accounts before creating and does not overwrite
existing configuration.
"""
from django.db import migrations


ACCOUNTS_RECEIVABLE_NAME = 'Accounts Receivable'
ACCOUNTS_RECEIVABLE_TYPE = 'ASSET'
ACCOUNTS_RECEIVABLE_DESC = (
    'System-managed asset account used for '
    'COD orders pending payment collection.'
)

SHIPPING_REVENUE_NAME = 'Shipping Revenue'
SHIPPING_REVENUE_TYPE = 'REVENUE'
SHIPPING_REVENUE_DESC = (
    'System-managed revenue account used when '
    'recording shipping charges on orders.'
)

COD_CASH_NAME = 'Cash - COD'
COD_CASH_TYPE = 'ASSET'
COD_CASH_DESC = (
    'Cash account for Cash on Delivery '
    'payment collection.'
)

COD_PM_CODE = 'COD'
COD_PM_NAME = 'Cash on Delivery'
COD_PM_DESC = (
    'Payment method for Cash on Delivery orders. '
    'Payment is collected by the delivery agent.'
)


def _get_or_create_account(
    AccountModel, name, acc_type, description
):
    """
    Idempotent account provisioning. Looks up by
    name + account_type. Reactivates if inactive.
    Returns the account.
    """
    account = AccountModel.objects.filter(
        name=name,
        account_type=acc_type,
    ).order_by('id').first()

    if account:
        update_fields = []
        if not account.is_active:
            account.is_active = True
            update_fields.append('is_active')
        if account.deleted_at is not None:
            account.deleted_at = None
            update_fields.append('deleted_at')
        if update_fields:
            update_fields.append('updated_at')
            account.save(update_fields=update_fields)
        return account

    return AccountModel.objects.create(
        name=name,
        account_type=acc_type,
        description=description,
    )


def seed_cod_infrastructure(apps, schema_editor):
    AccountModel = apps.get_model(
        'account_api', 'ChartOfAccount'
    )
    PaymentMethod = apps.get_model(
        'sale_api', 'PaymentMethod'
    )

    # 1. Accounts Receivable
    _get_or_create_account(
        AccountModel,
        ACCOUNTS_RECEIVABLE_NAME,
        ACCOUNTS_RECEIVABLE_TYPE,
        ACCOUNTS_RECEIVABLE_DESC,
    )

    # 2. Shipping Revenue
    _get_or_create_account(
        AccountModel,
        SHIPPING_REVENUE_NAME,
        SHIPPING_REVENUE_TYPE,
        SHIPPING_REVENUE_DESC,
    )

    # 3. Cash/Bank for COD
    cash_account = _get_or_create_account(
        AccountModel,
        COD_CASH_NAME,
        COD_CASH_TYPE,
        COD_CASH_DESC,
    )

    # 4. COD PaymentMethod
    pm, created = PaymentMethod.objects.get_or_create(
        code=COD_PM_CODE,
        defaults={
            'name': COD_PM_NAME,
            'description': COD_PM_DESC,
            'default_account': cash_account,
            'allow_account_override': False,
            'sort_order': 100,
        },
    )

    if not created:
        # Only reactivate if inactive/deleted.
        # Do NOT overwrite default_account or
        # allow_account_override — preserve existing
        # admin configuration.
        update_fields = []
        if not pm.is_active:
            pm.is_active = True
            update_fields.append('is_active')
        if pm.deleted_at is not None:
            pm.deleted_at = None
            update_fields.append('deleted_at')
        if update_fields:
            update_fields.append('updated_at')
            pm.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ('sale_api', '0011_alter_sale_idempotency_key'),
        (
            'account_api',
            '0008_rename_chart_of_ac_code_'
            '29cb81_idx_account_api_code_'
            'e60026_idx_and_more',
        ),
    ]

    operations = [
        migrations.RunPython(
            seed_cod_infrastructure,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
