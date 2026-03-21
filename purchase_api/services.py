# purchase_api/services.py
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from account_api.models import AccountType, ChartOfAccount
from inventory_api.models import InventoryMovement, MovementType, ReferenceType
from transaction_api.models import TransactionType
from transaction_api.services import create_transaction, post_transaction
from .models import Purchase, PurchaseItem, PurchaseStatus


INVENTORY_ASSET_ACCOUNT_NAME = 'Inventory Asset'
INVENTORY_ASSET_ACCOUNT_DESCRIPTION = (
    'System-managed asset account used for purchase inventory capitalization.'
)
ALLOWED_PURCHASE_ACCOUNT_TYPES = {
    AccountType.ASSET,
    AccountType.LIABILITY,
}


def _is_blank_invoice_number(value):
    return value is None or (isinstance(value, str) and not value.strip())


def _generate_purchase_invoice_number(purchase):
    return f"PUR-{purchase.purchase_date.strftime('%Y%m%d')}-{purchase.id:06d}"


def get_or_create_inventory_asset_account(user=None):
    with transaction.atomic():
        account = ChartOfAccount.objects.select_for_update().filter(
            name=INVENTORY_ASSET_ACCOUNT_NAME,
            account_type=AccountType.ASSET,
        ).order_by('id').first()

        if account:
            update_fields = []
            if not account.is_active:
                account.is_active = True
                update_fields.append('is_active')
            if account.deleted_at is not None:
                account.deleted_at = None
                update_fields.append('deleted_at')
            if user and account.updated_by_id != getattr(user, 'id', None):
                account.updated_by = user
                update_fields.append('updated_by')
            if update_fields:
                update_fields.append('updated_at')
                account.save(update_fields=update_fields)
            return account

        return ChartOfAccount.objects.create(
            name=INVENTORY_ASSET_ACCOUNT_NAME,
            account_type=AccountType.ASSET,
            description=INVENTORY_ASSET_ACCOUNT_DESCRIPTION,
            created_by=user,
            updated_by=user,
        )


def _validate_purchase_totals(instance):
    if instance.total_amount <= Decimal('0'):
        raise ValidationError({
            'detail': 'Purchase total amount must be greater than zero.'
        })


def _validate_purchase_account(account):
    if account is None:
        raise ValidationError({
            'account_id': 'An account must be selected before confirmation.'
        })

    if account.deleted_at is not None or not account.is_active:
        raise ValidationError({
            'account_id': 'The selected purchase account is inactive.'
        })

    if account.account_type not in ALLOWED_PURCHASE_ACCOUNT_TYPES:
        raise ValidationError({
            'account_id': (
                'Purchase account must be an asset or liability account.'
            )
        })


def _build_purchase_transaction_lines(purchase, inventory_account):
    amount = purchase.total_amount
    return [
        {
            'account': inventory_account,
            'description': f'Inventory received for purchase #{purchase.id}',
            'debit_amount': amount,
            'credit_amount': Decimal('0'),
        },
        {
            'account': purchase.account,
            'description': f'Purchase funding for purchase #{purchase.id}',
            'debit_amount': Decimal('0'),
            'credit_amount': amount,
        },
    ]


def _build_purchase_reference(purchase, suffix=None):
    base_reference = purchase.invoice_number or f'PUR-{purchase.id}'
    if suffix:
        return f'{base_reference}-{suffix}'[:100]
    return base_reference[:100]


def _create_purchase_transaction(user, purchase):
    inventory_account = get_or_create_inventory_asset_account(user=user)
    accounting_transaction = create_transaction(
        user,
        {
            'transaction_date': purchase.purchase_date,
            'transaction_type': TransactionType.PURCHASE,
            'reference': _build_purchase_reference(purchase),
            'description': (
                f'Purchase recorded for supplier {purchase.supplier.name}.'
            ),
            'lines': _build_purchase_transaction_lines(
                purchase,
                inventory_account,
            ),
        },
    )
    return post_transaction(user, accounting_transaction)


def _create_purchase_cancellation_transaction(user, purchase):
    inventory_account = get_or_create_inventory_asset_account(user=user)
    accounting_transaction = create_transaction(
        user,
        {
            'transaction_date': purchase.purchase_date,
            'transaction_type': TransactionType.ADJUSTMENT,
            'reference': _build_purchase_reference(purchase, suffix='CANCEL'),
            'description': (
                f'Purchase cancellation recorded for supplier '
                f'{purchase.supplier.name}.'
            ),
            'lines': [
                {
                    'account': purchase.account,
                    'description': (
                        f'Reversal of purchase funding for purchase '
                        f'#{purchase.id}'
                    ),
                    'debit_amount': purchase.total_amount,
                    'credit_amount': Decimal('0'),
                },
                {
                    'account': inventory_account,
                    'description': (
                        f'Reversal of inventory for purchase #{purchase.id}'
                    ),
                    'debit_amount': Decimal('0'),
                    'credit_amount': purchase.total_amount,
                },
            ],
        },
    )
    return post_transaction(user, accounting_transaction)


@transaction.atomic
def create_purchase(validated_data, user):
    items_data = validated_data.pop('items')
    if _is_blank_invoice_number(validated_data.get('invoice_number')):
        validated_data['invoice_number'] = None
    purchase = Purchase.objects.create(
        **validated_data,
        created_by=user,
        updated_by=user,
        status=PurchaseStatus.DRAFT
    )
    if not purchase.invoice_number:
        purchase.invoice_number = _generate_purchase_invoice_number(purchase)
        purchase.save(update_fields=['invoice_number'])
    for item_data in items_data:
        PurchaseItem.objects.create(purchase=purchase, **item_data)
    purchase.subtotal_amount, purchase.total_amount = purchase.calculate_totals()   # noqa
    purchase.save(update_fields=['subtotal_amount', 'total_amount'])
    return purchase


@transaction.atomic
def update_purchase(instance, validated_data, user):
    items_data = validated_data.pop('items', None)
    for attr, value in validated_data.items():
        setattr(instance, attr, value)
    instance.updated_by = user
    if items_data:
        instance.items.all().delete()
        for item_data in items_data:
            PurchaseItem.objects.create(purchase=instance, **item_data)
    instance.subtotal_amount, instance.total_amount = instance.calculate_totals()   # noqa
    instance.save()
    return instance


@transaction.atomic
def confirm_purchase(instance, user):
    if instance.status != PurchaseStatus.DRAFT:
        raise ValidationError("Only draft purchases can be confirmed.")
    if not instance.items.exists():
        raise ValidationError("Cannot confirm purchase with no items.")
    _validate_purchase_account(instance.account)
    _validate_purchase_totals(instance)
    if instance.accounting_transaction_id is not None:
        raise ValidationError({
            'detail': (
                'This purchase is already linked to an '
                'accounting transaction.'
            )
        })

    accounting_transaction = _create_purchase_transaction(user, instance)
    instance.status = PurchaseStatus.CONFIRMED
    instance.updated_by = user
    instance.accounting_transaction = accounting_transaction
    instance.save(update_fields=[
        'status',
        'accounting_transaction',
        'updated_by',
        'updated_at',
    ])
    for item in instance.items.all():
        InventoryMovement.objects.create(
            product_variant=item.product_variant,
            quantity=item.quantity,
            movement_type=MovementType.PURCHASE,
            reference_type=ReferenceType.PURCHASE,
            reference_id=instance.id,
            created_by=user
        )
    return instance


@transaction.atomic
def cancel_purchase(instance, user):
    if instance.status != PurchaseStatus.CONFIRMED:
        raise ValidationError("Only confirmed purchases can be cancelled.")
    _validate_purchase_account(instance.account)
    if instance.accounting_transaction_id is None:
        raise ValidationError({
            'detail': (
                'Confirmed purchase is missing its accounting '
                'transaction link.'
            )
        })
    if instance.cancellation_transaction_id is not None:
        raise ValidationError({
            'detail': 'This purchase already has a cancellation transaction.'
        })

    cancellation_transaction = _create_purchase_cancellation_transaction(
        user,
        instance,
    )
    instance.status = PurchaseStatus.CANCELLED
    instance.updated_by = user
    instance.cancellation_transaction = cancellation_transaction
    instance.save(update_fields=[
        'status',
        'cancellation_transaction',
        'updated_by',
        'updated_at',
    ])
    for item in instance.items.all():
        InventoryMovement.objects.create(
            product_variant=item.product_variant,
            quantity=-item.quantity,
            movement_type=MovementType.ADJUSTMENT,
            reference_type=ReferenceType.PURCHASE,
            reference_id=instance.id,
            created_by=user
        )
    return instance
