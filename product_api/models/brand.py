# product_api/models/brand.py
from django.db import models
from django.utils.text import slugify

from EcommerceBackend.core.models import (
    TimeStampedModel, UserStampedModel, SoftDeleteModel
)


class Brand(TimeStampedModel, UserStampedModel, SoftDeleteModel):
    """
    Brand model for product categorization.
    Represents manufacturers or brand names.
    """
    name = models.CharField(
        max_length=255,
        unique=True,
        db_index=True
    )
    slug = models.SlugField(
        max_length=255,
        unique=True,
        db_index=True
    )
    description = models.TextField(
        blank=True,
        null=True
    )
    display_order = models.PositiveIntegerField(
        default=1,
        db_index=True,
        help_text='Display order for brands. Lower values appear first.'
    )

    class Meta:
        db_table = 'brands'
        verbose_name = 'Brand'
        verbose_name_plural = 'Brands'
        ordering = ['display_order', 'name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['is_active']),
            models.Index(fields=['created_at']),
            models.Index(fields=['display_order']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.pk and not self.slug:
            self.slug = self._generate_unique_slug()
        super().save(*args, **kwargs)

    def _generate_unique_slug(self):
        """Generate a unique slug based on the brand name."""
        base_slug = slugify(self.name)
        slug = base_slug
        counter = 1

        qs = Brand.objects.filter(slug=slug)

        while qs.exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
            qs = Brand.objects.filter(slug=slug)

        return slug
