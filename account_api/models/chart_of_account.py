from django.db import models

from ZayrahLifeBackend.core.models import (
    SoftDeleteModel,
    TimeStampedModel,
    UserStampedModel,
)


class AccountType(models.TextChoices):
    ASSET = 'ASSET', 'Asset'
    LIABILITY = 'LIABILITY', 'Liability'
    EQUITY = 'EQUITY', 'Equity'
    REVENUE = 'REVENUE', 'Revenue'
    EXPENSE = 'EXPENSE', 'Expense'


class ChartOfAccount(TimeStampedModel, UserStampedModel, SoftDeleteModel):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    account_type = models.CharField(
        max_length=20,
        choices=AccountType.choices,
    )
    description = models.TextField(blank=True, null=True)
    parent = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        related_name='children',
        null=True,
        blank=True,
    )

    class Meta:
        db_table = 'chart_of_accounts'
        ordering = ['code', 'id']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['name']),
            models.Index(fields=['account_type']),
        ]

    def __str__(self):
        return f'{self.code} - {self.name}'
