# supplier_api/models.py
from django.db import models

from ZayrahLifeBackend.core.models import (
    TimeStampedModel, UserStampedModel, SoftDeleteModel
)
from category_api.models import Category


class PaymentType(models.TextChoices):
    COD = 'COD', 'Cash on Delivery'
    CREDIT = 'CREDIT', 'Credit'
    PREPAID = 'PREPAID', 'Prepaid'


class Supplier(TimeStampedModel, UserStampedModel, SoftDeleteModel):
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=100, blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    payment_type = models.CharField(max_length=20, choices=PaymentType.choices)
    credit_days = models.PositiveSmallIntegerField(null=True, blank=True)
    categories = models.ManyToManyField(
        Category,
        related_name='suppliers',
        blank=True,
    )

    class Meta:
        verbose_name = 'Supplier'
        verbose_name_plural = 'Suppliers'
        indexes = [
            models.Index(fields=['name'])
        ]
        ordering = ['name']

    def __str__(self):
        return self.name
