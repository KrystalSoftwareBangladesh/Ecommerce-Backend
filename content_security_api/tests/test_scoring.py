# content_security_api/tests/test_scoring.py
from django.test import SimpleTestCase

from content_security_api.models import RuleSeverity, ScanStatus
from content_security_api.services.scoring import (
    MAX_RISK_SCORE,
    calculate_risk_score,
    resolve_status,
    score,
    severity_weight,
)


class Finding:
    """
    Minimal stand-in carrying only what the scorer reads.
    """

    def __init__(self, severity):
        self.severity = severity


class SeverityWeightTests(SimpleTestCase):
    def test_approved_weights(self):
        self.assertEqual(severity_weight(RuleSeverity.INFO), 0)
        self.assertEqual(severity_weight(RuleSeverity.LOW), 10)
        self.assertEqual(severity_weight(RuleSeverity.MEDIUM), 25)
        self.assertEqual(severity_weight(RuleSeverity.HIGH), 50)
        self.assertEqual(severity_weight(RuleSeverity.CRITICAL), 80)

    def test_unknown_severity_contributes_nothing(self):
        self.assertEqual(severity_weight("UNKNOWN"), 0)


class RiskScoreTests(SimpleTestCase):
    def test_no_findings_score_zero(self):
        self.assertEqual(calculate_risk_score([]), 0)

    def test_findings_are_summed(self):
        findings = [
            Finding(RuleSeverity.HIGH),
            Finding(RuleSeverity.MEDIUM),
        ]

        self.assertEqual(calculate_risk_score(findings), 75)

    def test_score_is_capped(self):
        findings = [Finding(RuleSeverity.CRITICAL)] * 5

        self.assertEqual(calculate_risk_score(findings), MAX_RISK_SCORE)


class StatusThresholdTests(SimpleTestCase):
    def test_threshold_boundaries(self):
        self.assertEqual(resolve_status(0), ScanStatus.CLEAN)
        self.assertEqual(resolve_status(1), ScanStatus.LOW_RISK)
        self.assertEqual(resolve_status(24), ScanStatus.LOW_RISK)
        self.assertEqual(resolve_status(25), ScanStatus.REVIEW)
        self.assertEqual(resolve_status(49), ScanStatus.REVIEW)
        self.assertEqual(resolve_status(50), ScanStatus.HIGH_RISK)
        self.assertEqual(resolve_status(79), ScanStatus.HIGH_RISK)
        self.assertEqual(resolve_status(80), ScanStatus.CRITICAL)
        self.assertEqual(resolve_status(100), ScanStatus.CRITICAL)


class ScoreTests(SimpleTestCase):
    def test_clean_content(self):
        self.assertEqual(score([]), (0, ScanStatus.CLEAN))

    def test_one_low_finding_is_low_risk(self):
        self.assertEqual(
            score([Finding(RuleSeverity.LOW)]),
            (10, ScanStatus.LOW_RISK),
        )

    def test_one_medium_finding_needs_review(self):
        self.assertEqual(
            score([Finding(RuleSeverity.MEDIUM)]),
            (25, ScanStatus.REVIEW),
        )

    def test_one_high_finding_is_high_risk(self):
        self.assertEqual(
            score([Finding(RuleSeverity.HIGH)]),
            (50, ScanStatus.HIGH_RISK),
        )

    def test_one_critical_finding_is_critical(self):
        self.assertEqual(
            score([Finding(RuleSeverity.CRITICAL)]),
            (80, ScanStatus.CRITICAL),
        )

    def test_info_findings_do_not_raise_the_status(self):
        self.assertEqual(
            score([Finding(RuleSeverity.INFO)]),
            (0, ScanStatus.CLEAN),
        )
