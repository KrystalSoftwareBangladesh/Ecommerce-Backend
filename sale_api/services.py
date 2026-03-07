# sale_api/services.py
from django.db import transaction
from django.db.models import Sum
from django.core.exceptions import ValidationError

from .models import Sale, SaleItem, SaleStatus, get_next_sale_statuses
from inventory_api.models import InventoryMovement, MovementType, ReferenceType


def _is_blank_invoice_number(value):
    return value is None or (isinstance(value, str) and not value.strip())


def _generate_sale_invoice_number(sale):
    return f"SALE-{sale.sale_date.strftime('%Y%m%d')}-{sale.id:06d}"


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
        updatable_fields = [
            'customer', 'sale_date', 'invoice_number', 'channel',
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


def update_sale_status(user, sale, next_status):
    if sale.status == next_status:
        return sale

    allowed_statuses = get_next_sale_statuses(sale.status)
    if next_status not in allowed_statuses:
        raise ValidationError(
            f'Cannot change sale status from {sale.status} to {next_status}.'
        )

    with transaction.atomic():
        if next_status == SaleStatus.CONFIRMED:
            _deduct_sale_stock(user, sale)
        elif next_status == SaleStatus.RETURNED:
            _restock_returned_sale(user, sale)

        sale.status = next_status
        sale.updated_by = user
        sale.save(update_fields=['status', 'updated_by', 'updated_at'])
        return sale
