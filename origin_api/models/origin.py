from django.db import models
from django.utils.text import slugify

from EcommerceBackend.core.models import (
    TimeStampedModel, UserStampedModel, SoftDeleteModel
)


class Origin(TimeStampedModel, UserStampedModel, SoftDeleteModel):
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
    legacy_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        unique=True
    )

    class Meta:
        db_table = 'origins'
        verbose_name = 'Origin'
        verbose_name_plural = 'Origins'
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['is_active']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.pk and not self.slug:
            self.slug = self._generate_unique_slug()
        super().save(*args, **kwargs)

    def _generate_unique_slug(self):
        base_slug = slugify(self.name)
        slug = base_slug
        counter = 1

        qs = Origin.objects.filter(slug=slug)

        while qs.exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
            qs = Origin.objects.filter(slug=slug)

        return slug
