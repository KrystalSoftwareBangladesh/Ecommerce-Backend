# category_api/models/category.py
from django.db import models
from django.utils.text import slugify

from EcommerceBackend.core.models import (
    TimeStampedModel, UserStampedModel, SoftDeleteModel
)


class Category(TimeStampedModel, UserStampedModel, SoftDeleteModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    legacy_id = models.BigIntegerField(
        unique=True,
        null=True,
        blank=True,
        db_index=True,
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='subcategories'
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text='Display order for this category'
    )
    show_in_menu = models.BooleanField(
        default=False,
        db_index=True,
        help_text='Show this category in the storefront navigation menu'
    )

    class Meta:
        db_table = 'categories'
        verbose_name = 'Category'
        verbose_name_plural = 'Categories'
        ordering = ['display_order', 'name']
        permissions = [
            ('mark_category_as_menu', 'Can mark category as menu'),
            ('remove_category_from_menu', 'Can remove category from menu'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['name', 'parent'],
                name='unique_name_per_parent'
            ),
            models.UniqueConstraint(
                fields=['slug', 'parent'],
                name='unique_slug_per_parent'
            ),
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

        qs = Category.objects.filter(
            parent=self.parent,
            slug=slug
        )

        while qs.exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
            qs = Category.objects.filter(
                parent=self.parent,
                slug=slug
            )

        return slug
