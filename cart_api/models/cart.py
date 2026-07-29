# cart_api/models/__init__.py
from django.db import models
from django.db.models import (
    CASCADE,
    ForeignKey,
    PositiveIntegerField,
    Q,
    UniqueConstraint,
)

from EcommerceBackend.core.models import (
    SoftDeleteModel,
    TimeStampedModel,
    UserStampedModel,
)
from product_api.models import Product


class Cart(
    TimeStampedModel,
    UserStampedModel,
    SoftDeleteModel,
):
    product = ForeignKey(
        Product,
        on_delete=CASCADE,
        related_name="cart_items",
    )
    quantity = PositiveIntegerField(
        default=1,
    )

    class Meta:
        ordering = ["-created_at", "id"]

        constraints = [
            UniqueConstraint(
                fields=["product", "created_by"],
                condition=Q(is_active=True),
                name="unique_active_cart_item",
            ),
            models.CheckConstraint(
                condition=Q(quantity__gte=1),
                name="cart_quantity_gte_1",
            ),
        ]

        indexes = [
            models.Index(
                fields=["created_by", "-created_at"],
                name="cart_user_created_idx",
            ),
        ]

    def __str__(self):
        return f"{self.created_by} - {self.product} ({self.quantity})"
