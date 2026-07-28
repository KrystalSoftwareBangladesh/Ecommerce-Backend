# EcommerceBackend/core/models.py
from django.db import models
from django.utils import timezone

from .choices import ModerationStatus
from user_api.models import User


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        db_index=True
    )

    class Meta:
        abstract = True


class UserStampedModel(models.Model):
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_created"
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_updated"
    )

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    is_active = models.BooleanField(
        default=True,
        db_index=True
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True
    )

    class Meta:
        abstract = True

    def soft_delete(self):
        self.is_active = False
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_active", "deleted_at"])

    def restore(self):
        self.is_active = True
        self.deleted_at = None
        self.save(update_fields=["is_active", "deleted_at"])


class ModerationModel(models.Model):
    status = models.SmallIntegerField(
        choices=ModerationStatus.choices,
        default=ModerationStatus.PENDING,
        verbose_name="Moderation Status",
        db_index=True
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_approved"
    )

    class Meta:
        abstract = True

    def approve(self, user):
        self.status = ModerationStatus.APPROVED
        self.approved_at = timezone.now()
        self.approved_by = user
        self.save(update_fields=["status", "approved_at", "approved_by"])

    def reject(self):
        self.status = ModerationStatus.REJECTED
        self.approved_at = None
        self.approved_by = None
        self.save(update_fields=["status", "approved_at", "approved_by"])

    def reset_to_pending(self):
        self.status = ModerationStatus.PENDING
        self.approved_at = None
        self.approved_by = None
        self.save(update_fields=["status", "approved_at", "approved_by"])

    @property
    def is_approved(self):
        """Backward-compatible property for templates/serializers."""
        return self.status == ModerationStatus.APPROVED
