# banner_api/models/banner.py
from django.db import models

from EcommerceBackend.core.models import (
    TimeStampedModel,
    SoftDeleteModel,
    UserStampedModel,
)


class Banner(TimeStampedModel, SoftDeleteModel, UserStampedModel):
    placement = models.ForeignKey(
        "banner_api.BannerPlacement",
        on_delete=models.PROTECT,
        related_name="banners",
    )

    title = models.CharField(max_length=255, blank=True)
    subtitle = models.TextField(blank=True)

    image = models.ImageField(upload_to="banners/")
    mobile_image = models.ImageField(
        upload_to="banners/mobile/",
        blank=True,
        null=True,
    )

    cta_text = models.CharField(max_length=100, blank=True)
    cta_url = models.CharField(max_length=500, blank=True)

    display_order = models.PositiveIntegerField(
        default=0,
    )

    start_at = models.DateTimeField(blank=True, null=True)
    end_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["display_order", "-created_at"]
        indexes = [
            models.Index(fields=["placement", "is_active"]),
            models.Index(fields=["placement", "display_order"]),
            models.Index(fields=["start_at", "end_at"]),
        ]

    def __str__(self):
        return self.title or f"Banner #{self.pk}"
