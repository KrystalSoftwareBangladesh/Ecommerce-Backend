from django.db import models

from EcommerceBackend.core.models import (
    SoftDeleteModel,
    TimeStampedModel,
    UserStampedModel,
)

from .product import Product


class ProductImage(TimeStampedModel, UserStampedModel, SoftDeleteModel):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='images'
    )
    image = models.ImageField(
        upload_to='products/images/',
        max_length=500
    )
    alt_text = models.CharField(
        max_length=255,
        blank=True,
        default=''
    )
    display_order = models.PositiveIntegerField(
        default=0,
        db_index=True
    )
    is_default = models.BooleanField(
        default=False,
        db_index=True
    )

    class Meta:
        ordering = ['display_order', 'created_at']
        verbose_name = 'Product Image'
        verbose_name_plural = 'Product Images'
        indexes = [
            models.Index(fields=['product', 'display_order']),
            models.Index(fields=['product', 'is_default']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['product'],
                condition=models.Q(is_default=True, is_active=True),
                name='product_image_single_default_per_product',
            ),
        ]

    def __str__(self):
        return f"{self.product.name} image"
