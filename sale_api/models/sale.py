# sale_api/models/sale.py
from decimal import Decimal

from django.db import models
from EcommerceBackend.core.models import (
    TimeStampedModel, UserStampedModel, SoftDeleteModel
)
from account_api.models import ChartOfAccount
from customer_api.models import CustomerProfile
from product_api.models import ProductVariant
from .payment_method import PaymentMethod


class SaleStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    CONFIRMED = 'CONFIRMED', 'Confirmed'
    PROCESSING = 'PROCESSING', 'Processing'
    PACKAGED = 'PACKAGED', 'Packaged'
    SHIPPED = 'SHIPPED', 'Shipped'
    OUT_OF_DELIVERY = 'OUT_OF_DELIVERY', 'Out of Delivery'
    DELIVERED = 'DELIVERED', 'Delivered'
    RETURNED = 'RETURNED', 'Returned'
    CANCELLED = 'CANCELLED', 'Cancelled'


SALE_STATUS_TRANSITIONS = {
    SaleStatus.PENDING: [
        SaleStatus.CONFIRMED,
        SaleStatus.CANCELLED,
    ],
    SaleStatus.CONFIRMED: [SaleStatus.PROCESSING],
    SaleStatus.PROCESSING: [SaleStatus.PACKAGED],
    SaleStatus.PACKAGED: [SaleStatus.SHIPPED],
    SaleStatus.SHIPPED: [SaleStatus.OUT_OF_DELIVERY],
    SaleStatus.OUT_OF_DELIVERY: [SaleStatus.DELIVERED],
    SaleStatus.DELIVERED: [SaleStatus.RETURNED],
    SaleStatus.RETURNED: [],
    SaleStatus.CANCELLED: [],
}


class PaymentStatus(models.TextChoices):
    UNPAID = 'UNPAID', 'Unpaid'
    COLLECTED = 'COLLECTED', 'Collected'


def get_next_sale_statuses(current_status):
    return SALE_STATUS_TRANSITIONS.get(current_status, [])


class Sale(TimeStampedModel, UserStampedModel, SoftDeleteModel):
    class SaleChannel(models.TextChoices):
        WALK_IN = 'Walk-in', 'Walk-in'
        FACEBOOK = 'Facebook', 'Facebook'
        PHONE = 'Phone', 'Phone'
        WEBSITE = 'Website', 'Website'
        INSTAGRAM = 'Instagram', 'Instagram'
        WHATSAPP = 'WhatsApp', 'WhatsApp'

    customer = models.ForeignKey(CustomerProfile, on_delete=models.PROTECT)
    payment_method = models.ForeignKey(
        PaymentMethod,
        on_delete=models.PROTECT,
        related_name='sales',
        null=True,
        blank=True,
    )
    account = models.ForeignKey(
        ChartOfAccount,
        on_delete=models.PROTECT,
        related_name='sales',
        null=True,
        blank=True,
    )
    accounting_transaction = models.ForeignKey(
        'transaction_api.AccountingTransaction',
        on_delete=models.SET_NULL,
        related_name='sales',
        null=True,
        blank=True,
    )
    return_transaction = models.ForeignKey(
        'transaction_api.AccountingTransaction',
        on_delete=models.SET_NULL,
        related_name='returned_sales',
        null=True,
        blank=True,
    )
    sale_date = models.DateField()
    invoice_number = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        db_index=True,
    )
    channel = models.CharField(
        max_length=20,
        choices=SaleChannel.choices,
        default=SaleChannel.WALK_IN,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=SaleStatus.choices,
        default=SaleStatus.PENDING,
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
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID,
        db_index=True,
    )
    shipping_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
    )
    shipping_address_snapshot = models.JSONField(
        default=dict,
        blank=True,
    )
    idempotency_key = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text=(
            'Durable request fingerprint for idempotent '
            'order creation. Canonical hash of all '
            'meaningful request inputs.'
        ),
    )

    class Meta:
        unique_together = (
            ('invoice_number',),
            ('customer', 'idempotency_key'),
        )
        verbose_name = 'Sale'
        verbose_name_plural = 'Sales'
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['sale_date']),
            models.Index(
                fields=['customer', 'status'],
            ),
            models.Index(
                fields=['customer', 'payment_status'],
            ),
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
        verbose_name = 'Sale Item'
        verbose_name_plural = 'Sale Items'
