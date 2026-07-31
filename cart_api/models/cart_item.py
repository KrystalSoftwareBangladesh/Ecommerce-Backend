# cart_api/models/cart_item.py
from django.core.validators import MinValueValidator
from django.db import models

from EcommerceBackend.core.models import (
    SoftDeleteModel,
    TimeStampedModel,
)

from product_api.models import Product
from .cart import Cart


class CartItem(
    TimeStampedModel,
    SoftDeleteModel,
):
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="cart_items",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="cart_items",
    )
    quantity = models.PositiveIntegerField(
        default=1,
        validators=[
            MinValueValidator(1),
        ],
    )

    class Meta:
        ordering = (
            "created_at",
        )

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "cart",
                    "product",
                ],
                condition=models.Q(
                    is_active=True,
                ),
                name="unique_active_product_per_cart",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    quantity__gte=1,
                ),
                name="cart_item_quantity_gte_1",
            ),
        ]

    def __str__(self):
        return (
            f"{self.product} × {self.quantity}"
        )
