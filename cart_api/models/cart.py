# cart_api/models/cart.py
from django.db import models

from EcommerceBackend.core.models import (
    SoftDeleteModel, TimeStampedModel, UserStampedModel
)
from EcommerceBackend.core.choices import CartStatus
from .cart_type import CartType


class Cart(
    TimeStampedModel,
    UserStampedModel,
    SoftDeleteModel,
):
    name = models.CharField(
        max_length=255,
    )
    type = models.ForeignKey(
        CartType,
        on_delete=models.PROTECT,
        related_name="carts",
    )
    status = models.PositiveSmallIntegerField(
        choices=CartStatus.choices,
        default=CartStatus.ACTIVE,
        db_index=True,
    )
    is_default = models.BooleanField(
        default=False,
        db_index=True,
    )

    class Meta:
        ordering = (
            "-is_default",
            "-updated_at",
        )

    def __str__(self):
        return self.name
