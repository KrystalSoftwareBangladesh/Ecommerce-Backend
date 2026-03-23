from django.db import models

from ZayrahLifeBackend.core.models import (
    SoftDeleteModel,
    TimeStampedModel,
    UserStampedModel,
)
from account_api.models import ChartOfAccount


class PaymentMethod(TimeStampedModel, UserStampedModel, SoftDeleteModel):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    default_account = models.ForeignKey(
        ChartOfAccount,
        on_delete=models.PROTECT,
        related_name='payment_methods',
        null=True,
        blank=True,
    )
    allow_account_override = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'name', 'id']
        verbose_name = 'Payment Method'
        verbose_name_plural = 'Payment Methods'
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['name']),
            models.Index(fields=['sort_order']),
        ]

    def __str__(self):
        return self.name
