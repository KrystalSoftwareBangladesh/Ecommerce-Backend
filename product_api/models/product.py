# product_api/models/product.py
from django.db import models
from django.contrib.auth import get_user_model

from EcommerceBackend.core.models import (
    TimeStampedModel, UserStampedModel, SoftDeleteModel
)
from category_api.models import Category

User = get_user_model()


class Product(TimeStampedModel, UserStampedModel, SoftDeleteModel):
    name = models.CharField(max_length=200)
    categories = models.ManyToManyField(
        Category,
        related_name='products',
        blank=True
    )
    current_selling_price = models.DecimalField(
        max_digits=12, decimal_places=2)
    legacy_id = models.BigIntegerField(
        unique=True,
        null=True,
        blank=True,
    )
    slug = models.SlugField(
        max_length=255,
        unique=True,
    )
    description = models.TextField(blank=True)
    short_description = models.TextField(blank=True)
    specifications = models.TextField(blank=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        indexes = [models.Index(fields=['name'])]

    def __str__(self):
        return self.name


class ProductPriceHistory(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='price_histories'
    )
    price = models.DecimalField(max_digits=12, decimal_places=2)
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    class Meta:
        ordering = ['-changed_at']
        verbose_name = 'Product Price History'
        verbose_name_plural = 'Product Price Histories'


class ProductVariant(TimeStampedModel, SoftDeleteModel):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='variants'
    )
    sku = models.CharField(max_length=100)
    color = models.CharField(max_length=50, blank=True, null=True)
    size = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        ordering = ['sku']
        verbose_name = 'Product Variant'
        verbose_name_plural = 'Product Variants'
        indexes = [models.Index(fields=['sku'])]

    def __str__(self):
        return f"{self.sku} ({self.product.name})"
