# content_security_api/models/finding.py
from django.db import models

from EcommerceBackend.core.models import TimeStampedModel
from user_api.models import User

from content_security_api.constants import MATCHED_VALUE_MAX_LENGTH
from content_security_api.models.choices import (
    DetectorType,
    FindingReviewStatus,
    RuleCategory,
    RuleSeverity,
)
from content_security_api.models.scan import ContentScan


class ContentScanFinding(TimeStampedModel):
    """
    One structured detection produced by one detector during one scan.

    `rule_id_value` records which configured rule fired. It is a plain
    integer rather than a foreign key because the seven rule types are
    separate models; `rule_value` and `category` are denormalised from the
    rule so a finding stays readable after its rule is edited or deleted.
    """
    scan = models.ForeignKey(
        ContentScan,
        on_delete=models.CASCADE,
        related_name='findings',
    )
    detector = models.CharField(
        max_length=20,
        choices=DetectorType.choices,
        db_index=True,
    )
    rule_id_value = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name='Rule ID',
    )
    rule_value = models.CharField(
        max_length=MATCHED_VALUE_MAX_LENGTH,
        blank=True,
    )
    category = models.CharField(
        max_length=20,
        choices=RuleCategory.choices,
        db_index=True,
    )
    severity = models.CharField(
        max_length=10,
        choices=RuleSeverity.choices,
        db_index=True,
    )
    matched_value = models.CharField(
        max_length=MATCHED_VALUE_MAX_LENGTH,
        blank=True,
    )
    message = models.CharField(max_length=255)
    metadata = models.JSONField(default=dict, blank=True)
    review_status = models.CharField(
        max_length=15,
        choices=FindingReviewStatus.choices,
        default=FindingReviewStatus.PENDING,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='content_scan_findings_reviewed',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Content Scan Finding'
        verbose_name_plural = 'Content Scan Findings'
        ordering = ['scan', 'detector', 'id']
        permissions = [
            (
                'review_content_scan_finding',
                'Can review a content scan finding',
            ),
            (
                'resolve_content_scan_finding',
                'Can resolve a content scan finding',
            ),
        ]
        indexes = [
            models.Index(fields=['scan', 'detector']),
            models.Index(fields=['severity', 'review_status']),
        ]

    def __str__(self):
        return f'{self.detector}: {self.matched_value}'
