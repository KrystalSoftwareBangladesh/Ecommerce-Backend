# shipping_api/models/shipping_method.py
from django.db import models

from EcommerceBackend.core.models import (
    TimeStampedModel,
    UserStampedModel,
    SoftDeleteModel,
)


class ShippingMethod(
    TimeStampedModel,
    UserStampedModel,
    SoftDeleteModel,
):
    name = models.CharField(
        max_length=255,
        db_index=True,
    )
    code = models.SlugField(
        max_length=255,
        unique=True,
        db_index=True,
    )
    description = models.TextField(
        blank=True,
        default="",
    )
    display_order = models.PositiveIntegerField(
        default=1,
        db_index=True,
    )

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "Shipping Method"
        verbose_name_plural = "Shipping Methods"

    def __str__(self):
        return self.name
