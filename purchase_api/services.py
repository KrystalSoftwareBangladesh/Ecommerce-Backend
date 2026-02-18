# purchase_api/services.py
from django.db import transaction
# from django.utils import timezone

from .models import Purchase, PurchaseItem, PurchaseStatus
from inventory_api.models import InventoryMovement, MovementType, ReferenceType


@transaction.atomic
def create_purchase(validated_data, user):
    items_data = validated_data.pop('items')
    purchase = Purchase.objects.create(
        **validated_data,
        created_by=user,
        updated_by=user,
        status=PurchaseStatus.DRAFT
    )
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
        raise ValueError("Only draft purchases can be confirmed.")
    if not instance.items.exists():
        raise ValueError("Cannot confirm purchase with no items.")
    instance.status = PurchaseStatus.CONFIRMED
    instance.updated_by = user
    instance.save(update_fields=['status', 'updated_by', 'updated_at'])
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
        raise ValueError("Only confirmed purchases can be cancelled.")
    instance.status = PurchaseStatus.CANCELLED
    instance.updated_by = user
    instance.save(update_fields=['status', 'updated_by', 'updated_at'])
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
