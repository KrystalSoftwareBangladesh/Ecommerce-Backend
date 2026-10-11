# shipping_api/models/shipping_rate.py
from django.db import models
from django.core.exceptions import ValidationError

from EcommerceBackend.core.models import (
    TimeStampedModel,
    UserStampedModel,
    SoftDeleteModel,
)
from .shipping_zone import ShippingZone
from .shipping_method import ShippingMethod


class ShippingRate(
    TimeStampedModel,
    UserStampedModel,
    SoftDeleteModel,
):
    zone = models.ForeignKey(
        ShippingZone,
        on_delete=models.CASCADE,
        related_name="rates",
    )
    method = models.ForeignKey(
        ShippingMethod,
        on_delete=models.CASCADE,
        related_name="rates",
    )
    base_charge = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Base delivery charge in BDT.",
    )
    free_shipping_threshold = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=(
            "Order subtotal at or above which shipping "
            "is free. Leave blank to always charge."
        ),
    )

    class Meta:
        ordering = ["zone", "method"]
        indexes = [
            models.Index(fields=["zone", "method"]),
            models.Index(fields=["is_active"]),
        ]
        verbose_name = "Shipping Rate"
        verbose_name_plural = "Shipping Rates"

    def __str__(self):
        free = (
            " (free above "
            f"{self.free_shipping_threshold})"
            if self.free_shipping_threshold
            else ""
        )
        return (
            f"{self.zone.name} — {self.method.name} "
            f"@ {self.base_charge}{free}"
        )

    def clean(self):
        super().clean()
        if (
            self.base_charge < 0
        ):
            raise ValidationError(
                "base_charge must be >= 0."
            )
        if (
            self.free_shipping_threshold is not None
            and self.free_shipping_threshold < 0
        ):
            raise ValidationError(
                "free_shipping_threshold must be "
                ">= 0 when set."
            )
