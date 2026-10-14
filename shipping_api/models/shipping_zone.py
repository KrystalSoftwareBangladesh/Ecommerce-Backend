# shipping_api/models/shipping_zone.py
from django.db import models

from EcommerceBackend.core.models import (
    TimeStampedModel,
    UserStampedModel,
    SoftDeleteModel,
)


class ShippingZone(
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
    is_default = models.BooleanField(
        default=False,
        db_index=True,
        help_text=(
            "Use this zone when no other zone matches "
            "the delivery address."
        ),
    )

    class Meta:
        ordering = ["display_order", "name"]
        indexes = [
            models.Index(fields=["is_active", "is_default"]),
        ]
        verbose_name = "Shipping Zone"
        verbose_name_plural = "Shipping Zones"

    def __str__(self):
        default = " (default)" if self.is_default else ""
        return f"{self.name}{default}"

    def save(self, *args, **kwargs):
        if self.is_default:
            ShippingZone.objects.filter(
                is_default=True,
            ).exclude(pk=self.pk).update(
                is_default=False,
            )
        super().save(*args, **kwargs)


class ShippingZoneRule(TimeStampedModel, UserStampedModel):
    class MatchType(models.TextChoices):
        CITY = "CITY", "City"
        POSTCODE = "POSTCODE", "Postcode"

    zone = models.ForeignKey(
        ShippingZone,
        on_delete=models.CASCADE,
        related_name="rules",
    )
    match_type = models.CharField(
        max_length=20,
        choices=MatchType.choices,
        db_index=True,
    )
    match_value = models.CharField(
        max_length=255,
        help_text=(
            "Case-insensitive city or postcode to match. "
            "Postcodes are matched as prefix."
        ),
    )

    class Meta:
        ordering = ["match_type", "match_value"]
        indexes = [
            models.Index(
                fields=["match_type", "match_value"],
            ),
        ]
        verbose_name = "Shipping Zone Rule"
        verbose_name_plural = "Shipping Zone Rules"

    def __str__(self):
        return (
            f"{self.zone.name} — "
            f"{self.get_match_type_display()}: "
            f"{self.match_value}"
        )
