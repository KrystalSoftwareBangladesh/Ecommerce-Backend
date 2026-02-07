# products/models.py
from django.db import models
from django.contrib.auth import get_user_model
# from django.db.models import Sum, Value
# from django.db.models.functions import Coalesce

from ZayrahLifeBackend.core.models import (
    TimeStampedModel, UserStampedModel, SoftDeleteModel
)
from category_api.models import Category

User = get_user_model()


class Product(TimeStampedModel, UserStampedModel, SoftDeleteModel):
    name = models.CharField(max_length=200)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='products',
        null=True,
        blank=True
    )
    current_selling_price = models.DecimalField(
        max_digits=12, decimal_places=2)

    class Meta:
        ordering = ['name']
        indexes = [models.Index(fields=['name'])]

    def __str__(self):
        return self.name


class ProductPriceHistory(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='price_histories'
    )
    price = models.DecimalField(max_digits=12, decimal_places=2)
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    class Meta:
        ordering = ['-changed_at']


class ProductVariant(TimeStampedModel, SoftDeleteModel):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='variants'
    )
    sku = models.CharField(max_length=100)
    color = models.CharField(max_length=50, blank=True, null=True)
    size = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        ordering = ['sku']
        indexes = [models.Index(fields=['sku'])]

    def __str__(self):
        return f"{self.sku} ({self.product.name})"


# class MovementType(models.TextChoices):
#     PURCHASE = 'PURCHASE', 'Purchase'
#     SALE = 'SALE', 'Sale'
#     REFUND = 'REFUND', 'Refund'
#     ADJUSTMENT = 'ADJUSTMENT', 'Adjustment'
#     OPENING = 'OPENING', 'Opening Balance'


# class ReferenceType(models.TextChoices):
#     PURCHASE = 'PURCHASE', 'Purchase'
#     ORDER = 'ORDER', 'Order'
#     RETURN = 'RETURN', 'Return'
#     MANUAL = 'MANUAL', 'Manual'


# class InventoryMovement(TimeStampedModel):
#     product_variant = models.ForeignKey(
#         ProductVariant,
#         on_delete=models.PROTECT,
#         related_name='movements'
#     )
#     quantity = models.IntegerField()
#     movement_type = models.CharField(
#         max_length=20,
#         choices=MovementType.choices
#     )
#     reference_type = models.CharField(
#         max_length=20,
#         choices=ReferenceType.choices,
#         blank=True,
#         null=True
#     )
#     reference_id = models.PositiveBigIntegerField(blank=True, null=True)
#     created_by = models.ForeignKey(
#         User,
#         on_delete=models.SET_NULL,
#         null=True,
#         blank=True
#     )

#     class Meta:
#         ordering = ['-created_at']
#         indexes = [
#             models.Index(fields=['product_variant']),
#             models.Index(fields=['movement_type']),
#         ]
