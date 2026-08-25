# content_security_api/services/scoring.py
"""
Risk scoring.

Scoring lives here and nowhere else. Detectors report what they matched and
how severe the matching rule is; turning a set of findings into a single
`risk_score` and `status` is this module's sole responsibility.

Approved model
--------------
Weight per finding severity:

    INFO 0 | LOW 10 | MEDIUM 25 | HIGH 50 | CRITICAL 80

`risk_score` is the sum of the weights of the distinct findings, capped at
`MAX_RISK_SCORE`. Findings are deduplicated by (detector, rule, matched
value) before scoring, so the same match repeated in one field is counted
once and its repetitions are recorded in the finding metadata.

Status is derived from the score:

    0        CLEAN
    1  - 24  LOW_RISK
    25 - 49  REVIEW
    50 - 79  HIGH_RISK
    80 - 100 CRITICAL

Human review never changes either value. A finding marked as a false
positive stays in the record and keeps its weight, because the score is a
statement about what was detected, not about what was concluded.
"""
from content_security_api.models import RuleSeverity, ScanStatus


MAX_RISK_SCORE = 100

SEVERITY_WEIGHTS = {
    RuleSeverity.INFO: 0,
    RuleSeverity.LOW: 10,
    RuleSeverity.MEDIUM: 25,
    RuleSeverity.HIGH: 50,
    RuleSeverity.CRITICAL: 80,
}

# Lower bound of each status, highest first.
STATUS_THRESHOLDS = [
    (80, ScanStatus.CRITICAL),
    (50, ScanStatus.HIGH_RISK),
    (25, ScanStatus.REVIEW),
    (1, ScanStatus.LOW_RISK),
    (0, ScanStatus.CLEAN),
]


def severity_weight(severity):
    """
    Weight contributed by a single finding severity.
    """
    return SEVERITY_WEIGHTS.get(severity, 0)


def calculate_risk_score(findings):
    """
    Sum the weights of the given findings, capped at `MAX_RISK_SCORE`.
    """
    total = sum(severity_weight(finding.severity) for finding in findings)

    return min(total, MAX_RISK_SCORE)


def resolve_status(risk_score):
    """
    Map a risk score onto an overall content status.
    """
    for threshold, status in STATUS_THRESHOLDS:
        if risk_score >= threshold:
            return status

    return ScanStatus.CLEAN


def score(findings):
    """
    Return the `(risk_score, status)` pair for a set of findings.
    """
    risk_score = calculate_risk_score(findings)

    return risk_score, resolve_status(risk_score)
