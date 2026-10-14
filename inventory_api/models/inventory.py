# inventory_api/models/inventory.py
from django.db import models

from EcommerceBackend.core.models import (
    TimeStampedModel, UserStampedModel, SoftDeleteModel
)
from product_api.models import ProductVariant


class MovementType(models.TextChoices):
    PURCHASE = 'PURCHASE', 'Purchase'
    SALE = 'SALE', 'Sale'
    REFUND = 'REFUND', 'Refund'
    ADJUSTMENT = 'ADJUSTMENT', 'Adjustment'
    OPENING = 'OPENING', 'Opening Balance'


class ReferenceType(models.TextChoices):
    PURCHASE = 'PURCHASE', 'Purchase'
    ORDER = 'ORDER', 'Order'
    RETURN = 'RETURN', 'Return'
    MANUAL = 'MANUAL', 'Manual'


class InventoryMovement(TimeStampedModel, UserStampedModel, SoftDeleteModel):
    product_variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name='movements'
    )
    quantity = models.IntegerField()
    movement_type = models.CharField(
        max_length=20,
        choices=MovementType.choices
    )
    reference_type = models.CharField(
        max_length=20,
        choices=ReferenceType.choices,
        blank=True,
        null=True
    )
    reference_id = models.PositiveBigIntegerField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Inventory Movement'
        verbose_name_plural = 'Inventory Movements'
        indexes = [
            models.Index(fields=['product_variant']),
            models.Index(fields=['movement_type']),
        ]


class ReservationStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Active'
    CONSUMED = 'CONSUMED', 'Consumed'
    RELEASED = 'RELEASED', 'Released'


class InventoryReservation(
    TimeStampedModel, UserStampedModel
):
    product_variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name='reservations',
    )
    sale = models.ForeignKey(
        'sale_api.Sale',
        on_delete=models.CASCADE,
        related_name='reservations',
    )
    quantity = models.PositiveIntegerField()
    status = models.CharField(
        max_length=20,
        choices=ReservationStatus.choices,
        default=ReservationStatus.ACTIVE,
        db_index=True,
    )
    expires_at = models.DateTimeField()

    class Meta:
        verbose_name = 'Inventory Reservation'
        verbose_name_plural = 'Inventory Reservations'
        indexes = [
            models.Index(
                fields=['product_variant', 'status'],
            ),
            models.Index(
                fields=['sale', 'status'],
            ),
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        return (
            f"Reservation #{self.pk}: "
            f"{self.quantity} of "
            f"{self.product_variant} "
            f"({self.status})"
        )
