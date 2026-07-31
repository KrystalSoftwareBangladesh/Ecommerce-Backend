# cart_api/models/cart.py
from django.db import models

from EcommerceBackend.core.models import (
    SoftDeleteModel,
    TimeStampedModel,
    UserStampedModel,
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
        ordering = (
            "-created_at",
        )
        constraints = [
            models.UniqueConstraint(
                fields=["created_by"],
                condition=models.Q(
                    status=CartStatus.ACTIVE,
                    is_active=True,
                ),
                name="unique_active_cart_per_user",
            )
        ]

    def __str__(self):
        return (
            f"Cart #{self.pk} - "
            f"{self.created_by} - "
            f"{self.get_status_display()}"
        )
