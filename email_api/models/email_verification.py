# email_api/models/email_verification.py
from django.db import models

from EcommerceBackend.core.models import TimeStampedModel
from user_api.models import User


class EmailVerification(TimeStampedModel):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="email_verifications",
    )
    token_hash = models.CharField(
        max_length=64,
        unique=True,
    )
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["user", "expires_at"],
                name="email_ver_user_exp_idx",
            ),
        ]

    @property
    def is_verified(self):
        return self.verified_at is not None

    @property
    def is_expired(self):
        from django.utils import timezone

        return timezone.now() >= self.expires_at

    def __str__(self):
        return f"Email verification → {self.user.email}"
