# sale_api/models/sale.py
from django.db import models
from ZayrahLifeBackend.core.models import (
    TimeStampedModel, UserStampedModel, SoftDeleteModel
)
from customer_api.models import CustomerProfile
from product_api.models import ProductVariant


class Sale(TimeStampedModel, UserStampedModel, SoftDeleteModel):
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('CONFIRMED', 'Confirmed'),
        ('CANCELLED', 'Cancelled'),
    )
    customer = models.ForeignKey(CustomerProfile, on_delete=models.PROTECT)
    sale_date = models.DateField()
    invoice_number = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='DRAFT',
    )
    subtotal_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )
    discount_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )
    tax_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )
    total_amount = models.DecimalField(
        max_digits=15, decimal_places=2, default=0)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('invoice_number',)
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['sale_date']),
        ]


class SaleItem(models.Model):
    sale = models.ForeignKey(
        Sale, on_delete=models.CASCADE, related_name='items'
    )
    product_variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT
    )
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=15, decimal_places=2)
    line_total = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        unique_together = ('sale', 'product_variant')
