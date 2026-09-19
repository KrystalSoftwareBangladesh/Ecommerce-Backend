# banner_api/models/placement.py
from django.db import models

from EcommerceBackend.core.models import TimeStampedModel, SoftDeleteModel


class BannerPlacement(TimeStampedModel, SoftDeleteModel):
    name = models.CharField(max_length=100)
    code = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
