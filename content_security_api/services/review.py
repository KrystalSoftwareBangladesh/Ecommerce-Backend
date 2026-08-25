# content_security_api/services/review.py
"""
Human review of findings.

A finding is a detection, not a verdict. Review is where a person records
what the detection actually meant. Review never changes
`ContentScan.risk_score` or `ContentScan.status`, and it never alters the
scanned content.

    PENDING -> FALSE_POSITIVE            (terminal)
    PENDING -> CONFIRMED -> RESOLVED     (terminal)
"""
from django.db import transaction
from django.utils import timezone

from rest_framework.exceptions import ValidationError

from content_security_api.models import FindingReviewStatus


ALLOWED_TRANSITIONS = {
    FindingReviewStatus.PENDING: [
        FindingReviewStatus.FALSE_POSITIVE,
        FindingReviewStatus.CONFIRMED,
    ],
    FindingReviewStatus.CONFIRMED: [
        FindingReviewStatus.RESOLVED,
    ],
    FindingReviewStatus.FALSE_POSITIVE: [],
    FindingReviewStatus.RESOLVED: [],
}


@transaction.atomic
def review_finding(*, finding, user, review_status, note=''):
    """
    Record a review decision on a finding.
    """
    _assert_transition(finding.review_status, review_status)

    finding.review_status = review_status
    finding.reviewed_by = user
    finding.reviewed_at = timezone.now()
    finding.review_note = note or ''
    finding.save(update_fields=[
        'review_status',
        'reviewed_by',
        'reviewed_at',
        'review_note',
        'updated_at',
    ])

    return finding


def resolve_finding(*, finding, user, note=''):
    """
    Mark a confirmed finding as resolved.
    """
    return review_finding(
        finding=finding,
        user=user,
        review_status=FindingReviewStatus.RESOLVED,
        note=note,
    )


def _assert_transition(current, target):
    allowed = ALLOWED_TRANSITIONS.get(current, [])

    if target not in allowed:
        raise ValidationError(
            f'A finding cannot move from {current} to {target}.'
        )
