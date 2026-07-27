# wishlist_api/models/wishlist.py
from django.db import models
from django.db.models import (
    CASCADE,
    ForeignKey,
    Q,
    UniqueConstraint,
)

from EcommerceBackend.core.models import (
    SoftDeleteModel,
    TimeStampedModel,
    UserStampedModel,
)
from product_api.models import Product


class Wishlist(
    TimeStampedModel,
    UserStampedModel,
    SoftDeleteModel,
):
    product = ForeignKey(
        Product,
        on_delete=CASCADE,
        related_name="wishlist_items",
    )

    class Meta:
        ordering = ["-created_at", "id"]

        constraints = [
            UniqueConstraint(
                fields=["product", "created_by"],
                condition=Q(is_active=True),
                name="unique_active_wishlist_item",
            )
        ]

        indexes = [
            # Speeds up "My Wishlist" queries.
            models.Index(
                fields=["created_by", "-created_at"],
                name="wishlist_user_created_idx",
            ),
        ]

    def __str__(self):
        return f"{self.created_by} - {self.product}"
