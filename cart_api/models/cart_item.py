# cart_api/models/cart_item.py
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from EcommerceBackend.core.models import (
    SoftDeleteModel, TimeStampedModel
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
        related_name="items",
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="cart_items",
    )

    quantity = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
    )

    class Meta:
        db_table = "cart_item"
        verbose_name = "Cart Item"
        verbose_name_plural = "Cart Items"
        ordering = ["created_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["cart", "product"],
                condition=Q(is_active=True),
                name="unique_active_product_per_cart",
            ),
        ]

    def __str__(self):
        return f"Cart #{self.cart_id} - Product #{self.product_id}"
