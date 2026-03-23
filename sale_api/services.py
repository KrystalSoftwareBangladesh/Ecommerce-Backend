# sale_api/services.py
from decimal import Decimal

from account_api.models import AccountType, ChartOfAccount
from django.db import transaction
from django.db.models import Sum
from django.core.exceptions import ValidationError

from .models import (
    PaymentMethod,
    Sale,
    SaleItem,
    SaleStatus,
    get_next_sale_statuses,
)
from inventory_api.models import InventoryMovement, MovementType, ReferenceType
from transaction_api.models import TransactionType
from transaction_api.services import create_transaction, post_transaction


SALES_REVENUE_ACCOUNT_NAME = 'Sales Revenue'
SALES_REVENUE_ACCOUNT_DESCRIPTION = (
    'System-managed revenue account used when recording sales.'
)


def get_or_create_sales_revenue_account(user=None):
    with transaction.atomic():
        account = ChartOfAccount.objects.select_for_update().filter(
            name=SALES_REVENUE_ACCOUNT_NAME,
            account_type=AccountType.REVENUE,
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
            name=SALES_REVENUE_ACCOUNT_NAME,
            account_type=AccountType.REVENUE,
            description=SALES_REVENUE_ACCOUNT_DESCRIPTION,
            created_by=user,
            updated_by=user,
        )


def _is_blank_invoice_number(value):
    return value is None or (isinstance(value, str) and not value.strip())


def _generate_sale_invoice_number(sale):
    return f"SALE-{sale.sale_date.strftime('%Y%m%d')}-{sale.id:06d}"


def _validate_sale_totals(sale):
    if sale.total_amount <= Decimal('0'):
        raise ValidationError('Sale total amount must be greater than zero.')


def _validate_assignable_sale_account(account):
    if account is None:
        return

    if account.deleted_at is not None or not account.is_active:
        raise ValidationError('The selected sale account is inactive.')

    if account.account_type != AccountType.ASSET:
        raise ValidationError('Sale account must be an asset account.')


def _validate_payment_method(payment_method):
    if payment_method is None:
        return

    if payment_method.deleted_at is not None or not payment_method.is_active:
        raise ValidationError('The selected payment method is inactive.')


def _resolve_sale_account(payment_method, account):
    _validate_payment_method(payment_method)
    _validate_assignable_sale_account(account)

    if payment_method is None:
        return account

    default_account = payment_method.default_account
    if default_account is None:
        if account is not None:
            if not payment_method.allow_account_override:
                raise ValidationError(
                    'This payment method does not allow account override.'
                )
            return account
        raise ValidationError(
            'The selected payment method has no default account.'
        )

    _validate_assignable_sale_account(default_account)

    if account is None:
        return default_account

    if account.pk == default_account.pk:
        return account

    if not payment_method.allow_account_override:
        raise ValidationError(
            'The provided account is not allowed for the selected '
            'payment method.'
        )

    return account


def _validate_sale_account(account):
    if account is None:
        raise ValidationError({
            'account_id': 'An account must be selected before confirmation.'
        })

    if account.deleted_at is not None or not account.is_active:
        raise ValidationError({
            'account_id': 'The selected sale account is inactive.'
        })

    if account.account_type != AccountType.ASSET:
        raise ValidationError({
            'account_id': 'Sale account must be an asset account.'
        })


def _build_sale_reference(sale, suffix=None):
    base_reference = sale.invoice_number or f'SALE-{sale.id}'
    if suffix:
        return f'{base_reference}-{suffix}'[:100]
    return base_reference[:100]


def _build_sale_transaction_lines(sale, revenue_account):
    amount = sale.total_amount
    return [
        {
            'account': sale.account,
            'description': f'Sale receipt for sale #{sale.id}',
            'debit_amount': amount,
            'credit_amount': Decimal('0'),
        },
        {
            'account': revenue_account,
            'description': f'Sales revenue for sale #{sale.id}',
            'debit_amount': Decimal('0'),
            'credit_amount': amount,
        },
    ]


def _create_sale_transaction(user, sale):
    revenue_account = get_or_create_sales_revenue_account(user=user)
    accounting_transaction = create_transaction(
        user,
        {
            'transaction_date': sale.sale_date,
            'transaction_type': TransactionType.SALE,
            'reference': _build_sale_reference(sale),
            'description': (
                f'Sale recorded for customer {sale.customer}.'
            ),
            'lines': _build_sale_transaction_lines(sale, revenue_account),
        },
    )
    return post_transaction(user, accounting_transaction)


def _create_sale_return_transaction(user, sale):
    revenue_account = get_or_create_sales_revenue_account(user=user)
    accounting_transaction = create_transaction(
        user,
        {
            'transaction_date': sale.sale_date,
            'transaction_type': TransactionType.ADJUSTMENT,
            'reference': _build_sale_reference(sale, suffix='RETURN'),
            'description': (
                f'Sale return recorded for customer {sale.customer}.'
            ),
            'lines': [
                {
                    'account': revenue_account,
                    'description': f'Sales return for sale #{sale.id}',
                    'debit_amount': sale.total_amount,
                    'credit_amount': Decimal('0'),
                },
                {
                    'account': sale.account,
                    'description': f'Reversal of receipt for sale #{sale.id}',
                    'debit_amount': Decimal('0'),
                    'credit_amount': sale.total_amount,
                },
            ],
        },
    )
    return post_transaction(user, accounting_transaction)


def validate_stock(product_variant, quantity,):
    available = InventoryMovement.objects.filter(
        product_variant=product_variant,
    ).aggregate(stock=Sum('quantity'))['stock'] or 0
    if available < quantity:
        raise ValidationError(f'Insufficient stock for {product_variant}.')


def create_sale(user, data):
    with transaction.atomic():
        items_data = data.pop('items')
        if not items_data:
            raise ValidationError('At least one item required.')
        if _is_blank_invoice_number(data.get('invoice_number')):
            data['invoice_number'] = None
        data['account'] = _resolve_sale_account(
            data.get('payment_method'),
            data.get('account'),
        )
        sale = Sale(
            **data,
            created_by=user,
            updated_by=user,
            status=SaleStatus.PENDING,
            subtotal_amount=0,
            total_amount=0,
        )
        sale.save()
        if not sale.invoice_number:
            sale.invoice_number = _generate_sale_invoice_number(sale)
            sale.save(update_fields=['invoice_number'])
        subtotal = 0
        variants = set()
        for item_data in items_data:
            var = item_data['product_variant']
            if var in variants:
                raise ValidationError('Duplicate variant.')
            variants.add(var)
            qty = item_data['quantity']
            up = item_data['unit_price']
            lt = qty * up
            subtotal += lt
            item_payload = dict(item_data)
            item_payload.pop('line_total', None)
            SaleItem.objects.create(sale=sale, line_total=lt, **item_payload)
        sale.subtotal_amount = subtotal
        sale.total_amount = subtotal - sale.discount_amount + sale.tax_amount
        sale.save()
        return sale


def update_sale(user, sale, data):
    if sale.status != SaleStatus.PENDING:
        raise ValidationError('Cannot edit sale unless status is pending.')
    with transaction.atomic():
        if 'payment_method' in data or 'account' in data:
            payment_method = data.get('payment_method', sale.payment_method)
            account = data.get('account', sale.account)
            data['account'] = _resolve_sale_account(payment_method, account)
        updatable_fields = [
            'customer', 'payment_method', 'account', 'sale_date', 'channel',
            'discount_amount',
            'tax_amount', 'notes',
        ]
        for field in updatable_fields:
            if field in data:
                setattr(sale, field, data[field])
        sale.updated_by = user
        if 'items' in data:
            sale.items.all().delete()
            subtotal = 0
            variants = set()
            for item_data in data['items']:
                var = item_data['product_variant']
                if var in variants:
                    raise ValidationError('Duplicate variant.')
                variants.add(var)
                qty = item_data['quantity']
                up = item_data['unit_price']
                lt = qty * up
                subtotal += lt
                item_payload = dict(item_data)
                item_payload.pop('line_total', None)
                SaleItem.objects.create(  # noqa: E501
                    sale=sale, line_total=lt, **item_payload
                )
            sale.subtotal_amount = subtotal
        sale.total_amount = sale.subtotal_amount - \
            sale.discount_amount + sale.tax_amount
        sale.save()
        return sale


def _deduct_sale_stock(user, sale):
    for item in sale.items.all():
        validate_stock(
            item.product_variant,
            item.quantity,
        )
        InventoryMovement.objects.create(
            product_variant=item.product_variant,
            quantity=-item.quantity,
            movement_type=MovementType.SALE,
            reference_type=ReferenceType.ORDER,
            reference_id=sale.id,
            created_by=user
        )


def _restock_returned_sale(user, sale):
    for item in sale.items.all():
        InventoryMovement.objects.create(
            product_variant=item.product_variant,
            quantity=item.quantity,
            movement_type=MovementType.REFUND,
            reference_type=ReferenceType.RETURN,
            reference_id=sale.id,
            created_by=user
        )


def update_sale_status(
    user,
    sale,
    next_status,
    account=None,
    payment_method=None,
):
    if sale.status == next_status:
        return sale

    allowed_statuses = get_next_sale_statuses(sale.status)
    if next_status not in allowed_statuses:
        raise ValidationError(
            f'Cannot change sale status from {sale.status} to {next_status}.'
        )

    with transaction.atomic():
        if next_status == SaleStatus.CONFIRMED:
            if payment_method is not None:
                sale.payment_method = payment_method
            resolved_account = _resolve_sale_account(
                sale.payment_method,
                account if account is not None else sale.account,
            )
            sale.account = resolved_account
            _validate_sale_account(sale.account)
            _validate_sale_totals(sale)
            if sale.accounting_transaction_id is not None:
                raise ValidationError(
                    'This sale is already linked to an accounting transaction.'
                )
            _deduct_sale_stock(user, sale)
            sale.accounting_transaction = _create_sale_transaction(user, sale)
        elif next_status == SaleStatus.RETURNED:
            _validate_sale_account(sale.account)
            if sale.accounting_transaction_id is None:
                raise ValidationError(
                    'Confirmed sale is missing its accounting transaction link.'
                )
            if sale.return_transaction_id is not None:
                raise ValidationError(
                    'This sale already has a return transaction.'
                )
            _restock_returned_sale(user, sale)
            sale.return_transaction = _create_sale_return_transaction(
                user,
                sale,
            )

        sale.status = next_status
        sale.updated_by = user
        update_fields = ['status', 'updated_by', 'updated_at']
        if next_status == SaleStatus.CONFIRMED:
            update_fields.extend([
                'payment_method',
                'account',
                'accounting_transaction',
            ])
        elif next_status == SaleStatus.RETURNED:
            update_fields.append('return_transaction')
        sale.save(update_fields=update_fields)
        return sale
