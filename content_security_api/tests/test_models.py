# content_security_api/tests/test_models.py
from django.db.utils import IntegrityError
from django.test import TestCase
from django.utils import timezone

from content_security_api.constants import SCANNER_VERSION
from content_security_api.models import (
    ContentScan,
    ContentScanFinding,
    DetectorType,
    FindingReviewStatus,
    KeywordRule,
    RuleCategory,
    RuleSeverity,
    ScanContentType,
    ScanStatus,
)
from content_security_api.tests import factories


class DetectionRuleModelTests(TestCase):
    def test_rule_defaults_to_enabled_and_active(self):
        rule = factories.keyword_rule("casino")

        self.assertTrue(rule.is_enabled)
        self.assertTrue(rule.is_active)
        self.assertIsNone(rule.deleted_at)

    def test_soft_delete_is_separate_from_the_enabled_flag(self):
        rule = factories.keyword_rule("casino")

        rule.soft_delete()
        rule.refresh_from_db()

        self.assertTrue(rule.is_enabled)
        self.assertFalse(rule.is_active)
        self.assertIsNotNone(rule.deleted_at)

    def test_duplicate_active_keyword_rule_is_rejected(self):
        factories.keyword_rule("casino")

        with self.assertRaises(IntegrityError):
            factories.keyword_rule("casino")

    def test_categories_and_severities_are_the_approved_sets(self):
        self.assertEqual(
            [value for value, _ in RuleCategory.choices],
            [
                "GAMBLING", "ADULT", "DRUG", "MALWARE", "SCAM", "SPAM",
                "PHISHING", "REDIRECT", "INJECTION", "OBFUSCATION",
                "HIDDEN_CONTENT",
            ],
        )
        self.assertEqual(
            [value for value, _ in RuleSeverity.choices],
            ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"],
        )
        self.assertEqual(
            [value for value, _ in ScanStatus.choices],
            ["CLEAN", "LOW_RISK", "REVIEW", "HIGH_RISK", "CRITICAL"],
        )


class ContentScanModelTests(TestCase):
    def setUp(self):
        self.scan = ContentScan.objects.create(
            content_type=ScanContentType.PRODUCT,
            object_id=1,
            field_name="description",
            status=ScanStatus.HIGH_RISK,
            risk_score=75,
            scanned_at=timezone.now(),
        )

    def test_scan_stores_the_scanner_version_by_default(self):
        self.assertEqual(self.scan.scanner_version, SCANNER_VERSION)

    def test_scan_target_is_unique(self):
        with self.assertRaises(IntegrityError):
            ContentScan.objects.create(
                content_type=ScanContentType.PRODUCT,
                object_id=1,
                field_name="description",
                scanned_at=timezone.now(),
            )

    def test_findings_relate_to_their_scan(self):
        rule = factories.keyword_rule("casino")

        finding = ContentScanFinding.objects.create(
            scan=self.scan,
            detector=DetectorType.KEYWORD,
            rule_id_value=rule.pk,
            rule_value=rule.keyword,
            category=rule.category,
            severity=rule.severity,
            matched_value="casino",
            message="Suspicious keyword detected.",
        )

        self.assertEqual(list(self.scan.findings.all()), [finding])
        self.assertEqual(
            finding.review_status,
            FindingReviewStatus.PENDING,
        )
        self.assertEqual(finding.metadata, {})

    def test_deleting_a_scan_removes_its_findings(self):
        ContentScanFinding.objects.create(
            scan=self.scan,
            detector=DetectorType.KEYWORD,
            category=RuleCategory.GAMBLING,
            severity=RuleSeverity.HIGH,
            matched_value="casino",
            message="Suspicious keyword detected.",
        )

        self.scan.delete()

        self.assertEqual(ContentScanFinding.objects.count(), 0)

    def test_run_scan_permission_is_declared_on_the_model(self):
        codenames = [
            codename
            for codename, _ in ContentScan._meta.permissions
        ]

        self.assertIn("run_content_scan", codenames)

    def test_review_permissions_are_declared_on_the_finding(self):
        codenames = [
            codename
            for codename, _ in ContentScanFinding._meta.permissions
        ]

        self.assertIn("review_content_scan_finding", codenames)
        self.assertIn("resolve_content_scan_finding", codenames)


class SeedDataTests(TestCase):
    def test_technical_rules_are_seeded_and_keywords_are_not(self):
        from content_security_api.models import (
            DomainRule,
            HiddenContentRule,
            HtmlAttributeRule,
            HtmlTagRule,
            ObfuscationRule,
            RedirectRule,
        )

        self.assertEqual(KeywordRule.objects.count(), 0)
        self.assertEqual(DomainRule.objects.count(), 0)

        self.assertEqual(HtmlTagRule.objects.count(), 5)
        self.assertEqual(HtmlAttributeRule.objects.count(), 8)
        self.assertEqual(RedirectRule.objects.count(), 6)
        self.assertEqual(HiddenContentRule.objects.count(), 4)
        self.assertEqual(ObfuscationRule.objects.count(), 4)

    def test_script_tag_is_critical_and_iframe_is_high(self):
        from content_security_api.models import HtmlTagRule

        self.assertEqual(
            HtmlTagRule.objects.get(tag="script").severity,
            RuleSeverity.CRITICAL,
        )
        self.assertEqual(
            HtmlTagRule.objects.get(tag="iframe").severity,
            RuleSeverity.HIGH,
        )

    def test_base64_indicator_ships_disabled(self):
        from content_security_api.models import ObfuscationRule

        rule = ObfuscationRule.objects.get(indicator="BASE64")

        self.assertFalse(rule.is_enabled)
