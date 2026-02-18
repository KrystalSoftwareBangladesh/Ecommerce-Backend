# purchase_api/models/purchase.py
from django.db import models
from django.db.models import F, Sum

from ZayrahLifeBackend.core.models import (
    TimeStampedModel, UserStampedModel, SoftDeleteModel
)
from supplier_api.models import Supplier
from product_api.models import ProductVariant


class PurchaseStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    CONFIRMED = 'CONFIRMED', 'Confirmed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class Purchase(TimeStampedModel, UserStampedModel, SoftDeleteModel):
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name='purchases')
    purchase_date = models.DateField()
    invoice_number = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=PurchaseStatus.choices,
        default=PurchaseStatus.DRAFT
    )
    subtotal_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )
    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )
    tax_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-purchase_date', '-id']
        indexes = [
            models.Index(fields=['invoice_number']),
            models.Index(fields=['status']),
            models.Index(fields=['purchase_date']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['supplier', 'invoice_number'],
                condition=models.Q(invoice_number__isnull=False),
                name='unique_invoice_per_supplier'
            )
        ]

    def __str__(self):
        return f"Purchase {self.id} - {self.supplier.name}"

    def calculate_totals(self):
        aggregate = self.items.aggregate(
            subtotal=Sum(F('quantity') * F('unit_cost'))
        )
        subtotal = aggregate['subtotal'] or 0
        total = subtotal - self.discount_amount + self.tax_amount
        return subtotal, total


class PurchaseItem(TimeStampedModel):
    purchase = models.ForeignKey(
        Purchase, on_delete=models.CASCADE, related_name='items')
    product_variant = models.ForeignKey(
        ProductVariant, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(
        max_digits=12, decimal_places=2, editable=False)

    class Meta:
        ordering = ['id']

    def save(self, *args, **kwargs):
        self.line_total = self.quantity * self.unit_cost
        super().save(*args, **kwargs)
