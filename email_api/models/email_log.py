# email_api/models/email_log.py
from django.db import models

from EcommerceBackend.core.models import TimeStampedModel
from user_api.models import User

from email_api.constants import EmailStatus, EmailType


class EmailLog(TimeStampedModel):
    email_type = models.CharField(
        max_length=50,
        choices=EmailType.choices,
        db_index=True,
    )
    status = models.PositiveSmallIntegerField(
        choices=EmailStatus.choices,
        default=EmailStatus.PENDING,
        db_index=True,
    )

    recipient = models.EmailField()
    sender = models.EmailField()
    subject = models.CharField(max_length=255)

    provider = models.CharField(
        max_length=50,
        blank=True,
    )
    provider_message_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
    )

    related_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="email_logs",
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    error_message = models.TextField(
        blank=True,
    )

    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["email_type", "status"],
                name="email_log_type_status_idx",
            ),
            models.Index(
                fields=["recipient", "created_at"],
                name="email_log_rec_created_idx",
            ),
        ]

    def __str__(self):
        return f"{self.email_type} → {self.recipient}"
