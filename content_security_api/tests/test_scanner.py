# content_security_api/tests/test_scanner.py
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from content_security_api.constants import SCANNER_VERSION
from content_security_api.models import (
    ContentScan,
    ContentScanFinding,
    DetectorType,
    FindingReviewStatus,
    HtmlAttributePatternType,
    ObfuscationIndicator,
    RedirectMechanismType,
    ScanContentType,
    ScanStatus,
)
from content_security_api.services import (
    normalize,
    rescan,
    scan_all,
    scan_content_type,
    scan_field,
    scan_object,
)
from content_security_api.tests import factories


class NormalizationTests(TestCase):
    def test_entities_and_percent_encoding_are_decoded_once(self):
        content = normalize("&lt;script&gt; and %3Cb%3E")

        self.assertIn("<script>", content.normalized)
        self.assertIn("<b>", content.normalized)

    def test_raw_content_is_preserved_for_the_obfuscation_detector(self):
        content = normalize("&lt;script&gt;")

        self.assertEqual(content.raw, "&lt;script&gt;")

    def test_double_encoding_is_not_unwrapped_repeatedly(self):
        content = normalize("&amp;lt;script&amp;gt;")

        self.assertNotIn("<script>", content.normalized)

    def test_hosts_are_extracted_from_markup_and_bare_urls(self):
        content = normalize(
            '<a href="https://one.test/a">x</a> https://two.test/b'
        )

        self.assertEqual(
            sorted(content.hosts),
            ["one.test", "two.test"],
        )

    def test_relative_links_yield_no_host(self):
        content = normalize('<a href="/products/1">x</a>')

        self.assertEqual(content.hosts, {})

    def test_content_hash_is_stable(self):
        self.assertEqual(
            normalize("abc").content_hash,
            normalize("abc").content_hash,
        )


class ScanFieldTests(TestCase):
    def setUp(self):
        factories.clear_seeded_rules()
        factories.keyword_rule("casino")

    def test_clean_content_produces_a_clean_scan(self):
        scan = scan_field(
            content_type=ScanContentType.PRODUCT,
            object_id=1,
            field_name="description",
            content="A perfectly ordinary keyboard.",
        )

        self.assertEqual(scan.status, ScanStatus.CLEAN)
        self.assertEqual(scan.risk_score, 0)
        self.assertEqual(scan.findings.count(), 0)
        self.assertEqual(scan.scanner_version, SCANNER_VERSION)

    def test_findings_are_persisted_with_their_scan(self):
        scan = scan_field(
            content_type=ScanContentType.PRODUCT,
            object_id=1,
            field_name="description",
            content="Play at our casino.",
        )

        finding = scan.findings.get()

        self.assertEqual(finding.detector, DetectorType.KEYWORD)
        self.assertEqual(finding.matched_value, "casino")
        self.assertEqual(scan.risk_score, 50)
        self.assertEqual(scan.status, ScanStatus.HIGH_RISK)

    def test_multiple_detectors_contribute_to_one_scan(self):
        factories.html_tag_rule("script")
        factories.hidden_content_rule("display:none")

        scan = scan_field(
            content_type=ScanContentType.PRODUCT,
            object_id=1,
            field_name="description",
            content=(
                '<div style="display:none">casino</div>'
                '<script>x()</script>'
            ),
        )

        detectors = set(
            scan.findings.values_list("detector", flat=True)
        )

        self.assertEqual(
            detectors,
            {
                DetectorType.KEYWORD,
                DetectorType.HTML_TAG,
                DetectorType.HIDDEN_CONTENT,
            },
        )
        self.assertEqual(scan.risk_score, 100)
        self.assertEqual(scan.status, ScanStatus.CRITICAL)

    def test_findings_are_stored_worst_first(self):
        factories.html_tag_rule("script")

        scan = scan_field(
            content_type=ScanContentType.PRODUCT,
            object_id=1,
            field_name="description",
            content="casino <script></script>",
        )

        severities = list(
            scan.findings.values_list("severity", flat=True)
        )

        self.assertEqual(severities, ["CRITICAL", "HIGH"])

    def test_normalization_defeats_entity_encoded_evasion(self):
        factories.html_tag_rule("script")

        scan = scan_field(
            content_type=ScanContentType.PRODUCT,
            object_id=1,
            field_name="description",
            content="&lt;script&gt;alert(1)&lt;/script&gt;",
        )

        self.assertTrue(
            scan.findings.filter(
                detector=DetectorType.HTML_TAG
            ).exists()
        )

    def test_a_scan_target_is_updated_in_place(self):
        for _ in range(2):
            scan_field(
                content_type=ScanContentType.PRODUCT,
                object_id=1,
                field_name="description",
                content="casino",
            )

        self.assertEqual(ContentScan.objects.count(), 1)
        self.assertEqual(ContentScanFinding.objects.count(), 1)

    def test_content_is_never_modified(self):
        original = '<script>alert(1)</script> casino'

        scan_field(
            content_type=ScanContentType.PRODUCT,
            object_id=1,
            field_name="description",
            content=original,
        )

        self.assertEqual(original, '<script>alert(1)</script> casino')


class ProductAndCategoryScanTests(TestCase):
    def setUp(self):
        factories.clear_seeded_rules()
        factories.keyword_rule("casino")
        factories.redirect_rule("window.location")
        factories.html_attribute_rule(
            "javascript:",
            pattern_type=HtmlAttributePatternType.SCHEME,
            severity="CRITICAL",
        )

    def test_product_description_is_scanned(self):
        product = factories.product(description="Win big at the casino.")

        result = scan_object(
            content_type=ScanContentType.PRODUCT,
            obj=product,
        )

        scan = ContentScan.objects.get(
            content_type=ScanContentType.PRODUCT,
            object_id=product.pk,
            field_name="description",
        )

        self.assertEqual(result.scanned_fields, 3)
        self.assertEqual(scan.status, ScanStatus.HIGH_RISK)

    def test_product_short_description_is_scanned(self):
        product = factories.product(short_description="casino bonus")

        scan_object(content_type=ScanContentType.PRODUCT, obj=product)

        scan = ContentScan.objects.get(
            object_id=product.pk,
            field_name="short_description",
        )

        self.assertEqual(scan.findings.count(), 1)

    def test_product_specifications_are_scanned(self):
        product = factories.product(
            specifications="<script>window.location='x'</script>"
        )

        scan_object(content_type=ScanContentType.PRODUCT, obj=product)

        scan = ContentScan.objects.get(
            object_id=product.pk,
            field_name="specifications",
        )

        self.assertTrue(
            scan.findings.filter(
                detector=DetectorType.REDIRECT
            ).exists()
        )

    def test_category_description_is_scanned(self):
        category = factories.category(
            description='<a href="javascript:steal()">click</a>'
        )

        result = scan_object(
            content_type=ScanContentType.CATEGORY,
            obj=category,
        )

        scan = ContentScan.objects.get(
            content_type=ScanContentType.CATEGORY,
            object_id=category.pk,
        )

        self.assertEqual(result.scanned_fields, 1)
        self.assertEqual(scan.field_name, "description")
        self.assertEqual(scan.status, ScanStatus.CRITICAL)

    def test_only_the_registered_fields_are_scanned(self):
        product = factories.product(description="casino")

        scan_object(content_type=ScanContentType.PRODUCT, obj=product)

        self.assertEqual(
            sorted(
                ContentScan.objects.filter(
                    object_id=product.pk
                ).values_list("field_name", flat=True)
            ),
            ["description", "short_description", "specifications"],
        )

    def test_scanning_a_content_type_covers_every_object(self):
        factories.product(name="One", description="casino")
        factories.product(name="Two", description="clean copy")

        result = scan_content_type(content_type=ScanContentType.PRODUCT)

        self.assertEqual(result.scanned_objects, 2)
        self.assertEqual(result.flagged_fields, 1)

    def test_soft_deleted_products_are_not_scanned(self):
        product = factories.product(description="casino")
        product.soft_delete()

        result = scan_content_type(content_type=ScanContentType.PRODUCT)

        self.assertEqual(result.scanned_objects, 0)

    def test_scan_all_covers_products_and_categories(self):
        factories.product(description="casino")
        factories.category(description="casino")

        result = scan_all()

        self.assertEqual(
            set(
                ContentScan.objects.values_list(
                    "content_type", flat=True
                )
            ),
            {ScanContentType.PRODUCT, ScanContentType.CATEGORY},
        )
        self.assertEqual(result.scanned_objects, 2)


class RescanTests(TestCase):
    def setUp(self):
        factories.clear_seeded_rules()
        self.product = factories.product(
            description="Win big at the casino tonight."
        )

    def test_content_clean_under_the_old_rules_is_flagged_after_rescan(
        self
    ):
        scan_object(
            content_type=ScanContentType.PRODUCT,
            obj=self.product,
        )

        scan = ContentScan.objects.get(field_name="description")
        self.assertEqual(scan.status, ScanStatus.CLEAN)

        factories.keyword_rule("casino")

        refreshed = rescan(scan=scan)

        self.assertEqual(refreshed.status, ScanStatus.HIGH_RISK)
        self.assertEqual(refreshed.findings.count(), 1)

    def test_removing_a_rule_clears_the_finding_on_rescan(self):
        rule = factories.keyword_rule("casino")

        scan_object(
            content_type=ScanContentType.PRODUCT,
            obj=self.product,
        )
        scan = ContentScan.objects.get(field_name="description")
        self.assertEqual(scan.findings.count(), 1)

        rule.soft_delete()
        refreshed = rescan(scan=scan)

        self.assertEqual(refreshed.findings.count(), 0)
        self.assertEqual(refreshed.status, ScanStatus.CLEAN)

    def test_review_state_survives_a_rescan(self):
        factories.keyword_rule("casino")

        scan_object(
            content_type=ScanContentType.PRODUCT,
            obj=self.product,
        )
        scan = ContentScan.objects.get(field_name="description")

        finding = scan.findings.get()
        finding.review_status = FindingReviewStatus.FALSE_POSITIVE
        finding.review_note = "Product name mentions a casino theme."
        finding.save()

        refreshed = rescan(scan=scan)
        carried = refreshed.findings.get()

        self.assertEqual(
            carried.review_status,
            FindingReviewStatus.FALSE_POSITIVE,
        )
        self.assertEqual(
            carried.review_note,
            "Product name mentions a casino theme.",
        )

    def test_review_state_is_not_applied_to_a_different_finding(self):
        factories.keyword_rule("casino")

        scan_object(
            content_type=ScanContentType.PRODUCT,
            obj=self.product,
        )
        scan = ContentScan.objects.get(field_name="description")

        finding = scan.findings.get()
        finding.review_status = FindingReviewStatus.FALSE_POSITIVE
        finding.save()

        factories.keyword_rule("win", category="SCAM")

        refreshed = rescan(scan=scan)
        new_finding = refreshed.findings.get(rule_value="win")

        self.assertEqual(
            new_finding.review_status,
            FindingReviewStatus.PENDING,
        )

    def test_rescan_does_not_change_the_scanned_content(self):
        factories.keyword_rule("casino")

        scan_object(
            content_type=ScanContentType.PRODUCT,
            obj=self.product,
        )
        scan = ContentScan.objects.get(field_name="description")

        rescan(scan=scan)
        self.product.refresh_from_db()

        self.assertEqual(
            self.product.description,
            "Win big at the casino tonight.",
        )
        self.assertTrue(self.product.is_active)


class ScanContentCommandTests(TestCase):
    def setUp(self):
        factories.clear_seeded_rules()
        factories.keyword_rule("casino")

    def run_command(self, *args):
        out = StringIO()
        call_command("scan_content", *args, stdout=out)
        return out.getvalue()

    def test_full_scan_covers_products_and_categories(self):
        factories.product(description="casino")
        factories.category(description="casino")

        output = self.run_command()

        self.assertIn("Content scan complete.", output)
        self.assertEqual(
            set(
                ContentScan.objects.values_list(
                    "content_type", flat=True
                )
            ),
            {ScanContentType.PRODUCT, ScanContentType.CATEGORY},
        )

    def test_type_option_limits_the_scan(self):
        factories.product(description="casino")
        factories.category(description="casino")

        self.run_command("--type", "CATEGORY")

        self.assertEqual(
            set(
                ContentScan.objects.values_list(
                    "content_type", flat=True
                )
            ),
            {ScanContentType.CATEGORY},
        )

    def test_object_id_option_scans_one_object(self):
        product = factories.product(description="casino")
        factories.product(name="Other", description="casino")

        self.run_command(
            "--type", "PRODUCT",
            "--object-id", str(product.pk),
        )

        self.assertEqual(
            set(ContentScan.objects.values_list("object_id", flat=True)),
            {product.pk},
        )

    def test_object_id_requires_a_type(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            self.run_command("--object-id", "1")

    def test_command_reports_the_scanner_version(self):
        factories.product(description="casino")

        self.assertIn(
            f"Scanner version: {SCANNER_VERSION}",
            self.run_command(),
        )


class SeededRuleScanTests(TestCase):
    """
    The technical rules installed by the seed migration behave as approved
    without any extra configuration.
    """

    def test_script_tag_alone_is_critical(self):
        product = factories.product(
            description="<script>alert(1)</script>"
        )

        scan_object(content_type=ScanContentType.PRODUCT, obj=product)

        scan = ContentScan.objects.get(field_name="description")

        self.assertEqual(scan.status, ScanStatus.CRITICAL)
        self.assertEqual(scan.risk_score, 80)

    def test_hidden_content_alone_only_needs_review(self):
        product = factories.product(
            description='<div style="display:none">x</div>'
        )

        scan_object(content_type=ScanContentType.PRODUCT, obj=product)

        scan = ContentScan.objects.get(field_name="description")

        self.assertEqual(scan.status, ScanStatus.REVIEW)
        self.assertEqual(scan.risk_score, 25)

    def test_ordinary_migrated_markup_stays_clean(self):
        product = factories.product(
            description=(
                '<h2>Wi-Fi Router</h2><p>Dual band, '
                '<a href="https://example.test/x">specs</a>.</p>'
            )
        )

        scan_object(content_type=ScanContentType.PRODUCT, obj=product)

        scan = ContentScan.objects.get(field_name="description")

        self.assertEqual(scan.status, ScanStatus.CLEAN)

    def test_base64_indicator_is_off_so_data_uris_stay_clean(self):
        payload = "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
        product = factories.product(
            description=f'<img src="data:image/gif;base64,{payload}">'
        )

        scan_object(content_type=ScanContentType.PRODUCT, obj=product)

        scan = ContentScan.objects.get(field_name="description")

        self.assertFalse(
            scan.findings.filter(
                detector=DetectorType.OBFUSCATION
            ).exists()
        )

    def test_meta_refresh_is_detected_by_the_seeded_rule(self):
        product = factories.product(
            description=(
                '<meta http-equiv="refresh" content="0;url=https://x.test">'
            )
        )

        scan_object(content_type=ScanContentType.PRODUCT, obj=product)

        scan = ContentScan.objects.get(field_name="description")

        self.assertTrue(
            scan.findings.filter(
                detector=DetectorType.REDIRECT,
                rule_value="refresh",
            ).exists()
        )

    def test_seeded_redirect_and_obfuscation_rules_exist(self):
        self.assertTrue(
            ObfuscationIndicator.HTML_ENTITY
            in dict(ObfuscationIndicator.choices)
        )
        self.assertTrue(
            RedirectMechanismType.META_REFRESH
            in dict(RedirectMechanismType.choices)
        )
