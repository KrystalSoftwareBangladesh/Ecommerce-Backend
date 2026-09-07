# blog_api/models/blog_tag.py
from django.db import models
from django.utils.text import slugify

from EcommerceBackend.core.models import (
    TimeStampedModel, UserStampedModel, SoftDeleteModel
)


class BlogTag(TimeStampedModel, UserStampedModel, SoftDeleteModel):
    """
    A free-form label attached to blog posts.

    Deliberately separate from `Category`: a category is a curated,
    hierarchical branch of the catalogue reused by products, a tag is a
    flat editorial keyword owned by the blog.
    """
    name = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
    )
    slug = models.SlugField(
        max_length=255,
        unique=True,
        db_index=True,
    )
    legacy_id = models.BigIntegerField(
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text='Identifier of this tag in the system it was migrated '
                  'from. Set by migration tooling, not by the API.',
    )

    class Meta:
        verbose_name = 'Blog Tag'
        verbose_name_plural = 'Blog Tags'
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.pk and not self.slug:
            self.slug = self._generate_unique_slug()
        super().save(*args, **kwargs)

    def _generate_unique_slug(self):
        """Generate a unique slug based on the tag name."""
        base_slug = slugify(self.name)
        slug = base_slug
        counter = 1

        qs = BlogTag.objects.filter(slug=slug)

        while qs.exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
            qs = BlogTag.objects.filter(slug=slug)

        return slug
