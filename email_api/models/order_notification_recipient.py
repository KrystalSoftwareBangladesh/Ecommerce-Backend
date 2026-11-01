# email_api/models/order_notification_recipient.py
from django.db import models
from django.db.models import Q

from EcommerceBackend.core.models import (
    SoftDeleteModel,
    TimeStampedModel,
    UserStampedModel,
)


class OrderNotificationRecipient(
    TimeStampedModel,
    UserStampedModel,
    SoftDeleteModel,
):
    """
    An internal address notified when an order is placed or cancelled.

    The notification is a short alert for staff to act on, not a copy
    of the order. ``is_active`` pauses a recipient without removing
    it; a soft-deleted recipient (``deleted_at`` set) is gone.
    """
    email = models.EmailField(
        max_length=254,
        db_index=True,
    )
    name = models.CharField(
        max_length=120,
        blank=True,
        help_text='Optional label, e.g. "Warehouse" or a person.',
    )

    class Meta:
        verbose_name = 'Order Notification Recipient'
        verbose_name_plural = 'Order Notification Recipients'
        ordering = ['email', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['email'],
                condition=Q(deleted_at__isnull=True),
                name='order_notify_recipient_email_uniq',
            ),
        ]

    def __str__(self):
        return self.email
