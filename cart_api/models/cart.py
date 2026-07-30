# cart_api/models/cart.py
from django.db import models
from django.db.models import Q

from EcommerceBackend.core.models import (
    SoftDeleteModel, TimeStampedModel, UserStampedModel
)
from EcommerceBackend.core.choices import CartStatus


class Cart(
    TimeStampedModel,
    UserStampedModel,
    SoftDeleteModel,
):
    status = models.PositiveSmallIntegerField(
        choices=CartStatus.choices,
        default=CartStatus.ACTIVE,
        db_index=True,
    )

    class Meta:
        verbose_name = "Cart"
        verbose_name_plural = "Carts"
        ordering = ["-created_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["created_by"],
                condition=Q(
                    is_active=True,
                    status=CartStatus.ACTIVE,
                ),
                name="unique_active_cart_per_user",
            ),
        ]

    def __str__(self):
        return f"Cart #{self.pk}"
