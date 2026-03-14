from django.db import models

from ZayrahLifeBackend.core.models import (
    SoftDeleteModel,
    TimeStampedModel,
    UserStampedModel,
)
from account_api.models import ChartOfAccount


class TransactionStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    POSTED = 'POSTED', 'Posted'


class TransactionType(models.TextChoices):
    JOURNAL = 'JOURNAL', 'Journal'
    PAYMENT = 'PAYMENT', 'Payment'
    RECEIPT = 'RECEIPT', 'Receipt'
    PURCHASE = 'PURCHASE', 'Purchase'
    SALE = 'SALE', 'Sale'
    ADJUSTMENT = 'ADJUSTMENT', 'Adjustment'
    OPENING_BALANCE = 'OPENING_BALANCE', 'Opening Balance'
    TRANSFER = 'TRANSFER', 'Transfer'


class AccountingTransaction(
    TimeStampedModel,
    UserStampedModel,
    SoftDeleteModel,
):
    transaction_no = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        null=True,
    )
    transaction_date = models.DateField()
    transaction_type = models.CharField(
        max_length=30,
        choices=TransactionType.choices,
        default=TransactionType.JOURNAL,
    )
    reference = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=TransactionStatus.choices,
        default=TransactionStatus.DRAFT,
    )
    total_debit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    total_credit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    class Meta:
        ordering = ['-transaction_date', '-id']
        indexes = [
            models.Index(fields=['transaction_no']),
            models.Index(fields=['transaction_date']),
            models.Index(fields=['transaction_type']),
            models.Index(fields=['status']),
            models.Index(fields=['reference']),
        ]

    def __str__(self):
        return self.transaction_no or f'TRX-{self.pk}'


class AccountingTransactionLine(TimeStampedModel):
    transaction = models.ForeignKey(
        AccountingTransaction,
        on_delete=models.CASCADE,
        related_name='lines',
    )
    account = models.ForeignKey(
        ChartOfAccount,
        on_delete=models.PROTECT,
        related_name='transaction_lines',
    )
    description = models.TextField(blank=True, null=True)
    debit_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    credit_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.account} ({self.transaction})'
