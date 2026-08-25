# content_security_api/models/scan.py
from django.db import models

from EcommerceBackend.core.models import TimeStampedModel

from content_security_api.constants import SCANNER_VERSION
from content_security_api.models.choices import ScanContentType, ScanStatus


class ContentScan(TimeStampedModel):
    """
    Result of scanning one field of one object.

    The scanned object is referenced with a `content_type` choice plus an
    `object_id`, mirroring the `reference_type` / `reference_id` pattern
    already used by `inventory_api.InventoryMovement`. There is exactly one
    row per (content_type, object_id, field_name); a re-scan updates it in
    place.
    """
    content_type = models.CharField(
        max_length=20,
        choices=ScanContentType.choices,
        db_index=True,
    )
    object_id = models.PositiveBigIntegerField(db_index=True)
    field_name = models.CharField(max_length=100, db_index=True)
    status = models.CharField(
        max_length=10,
        choices=ScanStatus.choices,
        default=ScanStatus.CLEAN,
        db_index=True,
    )
    risk_score = models.PositiveSmallIntegerField(
        default=0,
        db_index=True,
    )
    scanner_version = models.CharField(
        max_length=20,
        default=SCANNER_VERSION,
        db_index=True,
    )
    content_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text=(
            'SHA-256 of the scanned content, recorded so stale or unchanged '
            'content can be identified later.'
        ),
    )
    scanned_at = models.DateTimeField(db_index=True)

    class Meta:
        verbose_name = 'Content Scan'
        verbose_name_plural = 'Content Scans'
        ordering = ['-risk_score', '-scanned_at']
        permissions = [
            ('run_content_scan', 'Can run a content security scan'),
        ]
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['status', 'risk_score']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['content_type', 'object_id', 'field_name'],
                name='content_security_unique_scan_target',
            ),
        ]

    def __str__(self):
        return f'{self.content_type} #{self.object_id} {self.field_name}'
