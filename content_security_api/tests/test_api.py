# content_security_api/tests/test_api.py
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

from rest_framework.test import APITestCase

from user_api.models import User

from content_security_api.models import (
    ContentScan,
    ContentScanFinding,
    FindingReviewStatus,
    KeywordRule,
    ScanContentType,
    ScanStatus,
)
from content_security_api.services import scan_object
from content_security_api.tests import factories


SCANS_URL = '/api/v1/content-security/scans/'
FINDINGS_URL = '/api/v1/content-security/findings/'
KEYWORD_RULES_URL = '/api/v1/content-security/keyword-rules/'
DOMAIN_RULES_URL = '/api/v1/content-security/domain-rules/'
HTML_TAG_RULES_URL = '/api/v1/content-security/html-tag-rules/'
HTML_ATTRIBUTE_RULES_URL = (
    '/api/v1/content-security/html-attribute-rules/'
)


def grant(user, model, codename):
    content_type = ContentType.objects.get_for_model(model)
    user.user_permissions.add(
        Permission.objects.get(
            content_type=content_type,
            codename=codename,
        )
    )
    return User.objects.get(pk=user.pk)


class ContentSecurityApiTestCase(APITestCase):
    def setUp(self):
        factories.clear_seeded_rules()

        self.user = User.objects.create_user(
            username='security-staff',
            email='security-staff@example.com',
            password='test-pass-123',
            role='STAFF',
        )
        self.superuser = User.objects.create_superuser(
            username='security-admin',
            email='security-admin@example.com',
            password='test-pass-123',
        )

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.user)


class AuthenticationTests(ContentSecurityApiTestCase):
    def test_scan_list_requires_authentication(self):
        self.assertEqual(self.client.get(SCANS_URL).status_code, 401)

    def test_finding_list_requires_authentication(self):
        self.assertEqual(self.client.get(FINDINGS_URL).status_code, 401)

    def test_rule_list_requires_authentication(self):
        self.assertEqual(
            self.client.get(KEYWORD_RULES_URL).status_code,
            401,
        )

    def test_nothing_is_publicly_readable(self):
        for url in [
            SCANS_URL,
            FINDINGS_URL,
            KEYWORD_RULES_URL,
            DOMAIN_RULES_URL,
            HTML_TAG_RULES_URL,
        ]:
            self.assertEqual(self.client.get(url).status_code, 401, url)


class ScanApiTests(ContentSecurityApiTestCase):
    def setUp(self):
        super().setUp()
        factories.keyword_rule('casino')
        self.product = factories.product(description='casino night')
        self.category = factories.category(description='clean copy')

        scan_object(
            content_type=ScanContentType.PRODUCT,
            obj=self.product,
        )
        scan_object(
            content_type=ScanContentType.CATEGORY,
            obj=self.category,
        )

    def test_list_returns_the_paginated_shape(self):
        self.authenticate()

        response = self.client.get(SCANS_URL)

        self.assertEqual(response.status_code, 200)
        for key in ['count', 'total_pages', 'current_page', 'results']:
            self.assertIn(key, response.data)

    def test_list_is_paginated_by_page_size(self):
        self.authenticate()

        response = self.client.get(f'{SCANS_URL}?page_size=2')

        self.assertEqual(len(response.data['results']), 2)
        self.assertEqual(response.data['count'], 4)

    def test_list_carries_the_finding_count(self):
        self.authenticate()

        response = self.client.get(f'{SCANS_URL}?status=HIGH_RISK')

        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['finding_count'], 1)

    def test_filter_by_content_type(self):
        self.authenticate()

        response = self.client.get(f'{SCANS_URL}?content_type=CATEGORY')

        self.assertEqual(response.data['count'], 1)

    def test_filter_by_field_name_and_object_id(self):
        self.authenticate()

        response = self.client.get(
            f'{SCANS_URL}?field_name=description'
            f'&object_id={self.product.pk}'
            '&content_type=PRODUCT'
        )

        self.assertEqual(response.data['count'], 1)

    def test_filter_by_risk_score_range(self):
        self.authenticate()

        response = self.client.get(f'{SCANS_URL}?risk_score_min=50')

        self.assertEqual(response.data['count'], 1)

    def test_ordering_by_risk_score(self):
        self.authenticate()

        response = self.client.get(f'{SCANS_URL}?ordering=-risk_score')

        scores = [row['risk_score'] for row in response.data['results']]

        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_detail_embeds_findings_and_the_object_label(self):
        self.authenticate()

        scan = ContentScan.objects.get(
            content_type=ScanContentType.PRODUCT,
            object_id=self.product.pk,
            field_name='description',
        )

        response = self.client.get(f'{SCANS_URL}{scan.pk}/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['object_label'], self.product.name)
        self.assertEqual(len(response.data['findings']), 1)

    def test_starting_a_scan_requires_the_run_permission(self):
        self.authenticate()

        response = self.client.post(
            SCANS_URL,
            {
                'content_type': 'PRODUCT',
                'object_id': self.product.pk,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 403)

    def test_starting_a_scan_with_the_permission_succeeds(self):
        user = grant(self.user, ContentScan, 'run_content_scan')
        self.authenticate(user)

        response = self.client.post(
            SCANS_URL,
            {
                'content_type': 'PRODUCT',
                'object_id': self.product.pk,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['scanned_objects'], 1)
        self.assertEqual(response.data['scanned_fields'], 3)
        self.assertEqual(response.data['total_findings'], 1)
        self.assertEqual(
            response.data['status_counts'][ScanStatus.HIGH_RISK],
            1,
        )

    def test_starting_a_scan_can_narrow_the_fields(self):
        user = grant(self.user, ContentScan, 'run_content_scan')
        self.authenticate(user)

        response = self.client.post(
            SCANS_URL,
            {
                'content_type': 'PRODUCT',
                'object_id': self.product.pk,
                'field_names': ['description'],
            },
            format='json',
        )

        self.assertEqual(response.data['scanned_fields'], 1)

    def test_starting_a_scan_rejects_an_unsupported_field(self):
        user = grant(self.user, ContentScan, 'run_content_scan')
        self.authenticate(user)

        response = self.client.post(
            SCANS_URL,
            {
                'content_type': 'PRODUCT',
                'object_id': self.product.pk,
                'field_names': ['name'],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)

    def test_starting_a_scan_rejects_an_unknown_object(self):
        user = grant(self.user, ContentScan, 'run_content_scan')
        self.authenticate(user)

        response = self.client.post(
            SCANS_URL,
            {'content_type': 'PRODUCT', 'object_id': 999999},
            format='json',
        )

        self.assertEqual(response.status_code, 400)

    def test_rescan_requires_the_run_permission(self):
        self.authenticate()

        scan = ContentScan.objects.first()

        response = self.client.post(f'{SCANS_URL}{scan.pk}/rescan/')

        self.assertEqual(response.status_code, 403)

    def test_rescan_applies_a_newly_added_rule(self):
        user = grant(self.user, ContentScan, 'run_content_scan')
        self.authenticate(user)

        scan = ContentScan.objects.get(
            content_type=ScanContentType.CATEGORY,
        )
        self.assertEqual(scan.status, ScanStatus.CLEAN)

        factories.keyword_rule('clean copy', category='SPAM')

        response = self.client.post(f'{SCANS_URL}{scan.pk}/rescan/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], ScanStatus.HIGH_RISK)

    def test_scans_cannot_be_deleted_through_the_api(self):
        user = grant(self.user, ContentScan, 'run_content_scan')
        self.authenticate(user)

        scan = ContentScan.objects.first()

        self.assertEqual(
            self.client.delete(f'{SCANS_URL}{scan.pk}/').status_code,
            405,
        )


class FindingApiTests(ContentSecurityApiTestCase):
    def setUp(self):
        super().setUp()
        factories.keyword_rule('casino')
        factories.html_tag_rule('script')

        self.product = factories.product(
            description='casino <script>x()</script>'
        )
        scan_object(
            content_type=ScanContentType.PRODUCT,
            obj=self.product,
        )

        self.finding = ContentScanFinding.objects.get(
            detector='KEYWORD',
        )

    def test_list_returns_every_finding(self):
        self.authenticate()

        response = self.client.get(FINDINGS_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 2)

    def test_filter_by_detector(self):
        self.authenticate()

        response = self.client.get(f'{FINDINGS_URL}?detector=HTML_TAG')

        self.assertEqual(response.data['count'], 1)

    def test_filter_by_severity_and_category(self):
        self.authenticate()

        response = self.client.get(
            f'{FINDINGS_URL}?severity=CRITICAL&category=INJECTION'
        )

        self.assertEqual(response.data['count'], 1)

    def test_filter_by_scanned_object(self):
        self.authenticate()

        response = self.client.get(
            f'{FINDINGS_URL}?content_type=PRODUCT'
            f'&object_id={self.product.pk}'
            '&field_name=description'
        )

        self.assertEqual(response.data['count'], 2)

    def test_search_by_matched_value(self):
        self.authenticate()

        response = self.client.get(f'{FINDINGS_URL}?search=casino')

        self.assertEqual(response.data['count'], 1)

    def test_detail_exposes_the_metadata(self):
        self.authenticate()

        response = self.client.get(f'{FINDINGS_URL}{self.finding.pk}/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['metadata']['occurrences'], 1)
        self.assertEqual(response.data['field_name'], 'description')

    def test_review_requires_the_review_permission(self):
        self.authenticate()

        response = self.client.post(
            f'{FINDINGS_URL}{self.finding.pk}/review/',
            {'review_status': 'FALSE_POSITIVE'},
            format='json',
        )

        self.assertEqual(response.status_code, 403)

    def test_marking_a_finding_as_a_false_positive(self):
        user = grant(
            self.user,
            ContentScanFinding,
            'review_content_scan_finding',
        )
        self.authenticate(user)

        response = self.client.post(
            f'{FINDINGS_URL}{self.finding.pk}/review/',
            {
                'review_status': 'FALSE_POSITIVE',
                'review_note': 'Casino-themed product, not spam.',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data['review_status'],
            FindingReviewStatus.FALSE_POSITIVE,
        )
        self.assertEqual(response.data['reviewed_by'], str(user))
        self.assertIsNotNone(response.data['reviewed_at'])

    def test_review_does_not_change_the_scan_risk(self):
        user = grant(
            self.user,
            ContentScanFinding,
            'review_content_scan_finding',
        )
        self.authenticate(user)

        scan = self.finding.scan
        before = (scan.risk_score, scan.status)

        self.client.post(
            f'{FINDINGS_URL}{self.finding.pk}/review/',
            {'review_status': 'FALSE_POSITIVE'},
            format='json',
        )

        scan.refresh_from_db()

        self.assertEqual((scan.risk_score, scan.status), before)

    def test_a_false_positive_cannot_be_reviewed_again(self):
        user = grant(
            self.user,
            ContentScanFinding,
            'review_content_scan_finding',
        )
        self.authenticate(user)

        url = f'{FINDINGS_URL}{self.finding.pk}/review/'
        self.client.post(
            url,
            {'review_status': 'FALSE_POSITIVE'},
            format='json',
        )

        response = self.client.post(
            url,
            {'review_status': 'CONFIRMED'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)

    def test_review_rejects_an_unsupported_status(self):
        user = grant(
            self.user,
            ContentScanFinding,
            'review_content_scan_finding',
        )
        self.authenticate(user)

        response = self.client.post(
            f'{FINDINGS_URL}{self.finding.pk}/review/',
            {'review_status': 'RESOLVED'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)

    def test_resolve_requires_the_resolve_permission(self):
        user = grant(
            self.user,
            ContentScanFinding,
            'review_content_scan_finding',
        )
        self.authenticate(user)

        self.client.post(
            f'{FINDINGS_URL}{self.finding.pk}/review/',
            {'review_status': 'CONFIRMED'},
            format='json',
        )

        response = self.client.post(
            f'{FINDINGS_URL}{self.finding.pk}/resolve/'
        )

        self.assertEqual(response.status_code, 403)

    def test_resolving_a_confirmed_finding(self):
        self.authenticate(self.superuser)

        self.client.post(
            f'{FINDINGS_URL}{self.finding.pk}/review/',
            {'review_status': 'CONFIRMED'},
            format='json',
        )

        response = self.client.post(
            f'{FINDINGS_URL}{self.finding.pk}/resolve/',
            {'review_note': 'Description rewritten by hand.'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data['review_status'],
            FindingReviewStatus.RESOLVED,
        )

    def test_a_pending_finding_cannot_be_resolved_directly(self):
        self.authenticate(self.superuser)

        response = self.client.post(
            f'{FINDINGS_URL}{self.finding.pk}/resolve/'
        )

        self.assertEqual(response.status_code, 400)

    def test_findings_cannot_be_edited_through_the_api(self):
        self.authenticate(self.superuser)

        response = self.client.patch(
            f'{FINDINGS_URL}{self.finding.pk}/',
            {'severity': 'INFO'},
            format='json',
        )

        self.assertEqual(response.status_code, 405)


class RuleApiTests(ContentSecurityApiTestCase):
    def test_listing_rules_requires_the_view_permission(self):
        self.authenticate()

        self.assertEqual(
            self.client.get(KEYWORD_RULES_URL).status_code,
            403,
        )

    def test_listing_rules_with_the_view_permission(self):
        factories.keyword_rule('casino')
        user = grant(self.user, KeywordRule, 'view_keywordrule')
        self.authenticate(user)

        response = self.client.get(KEYWORD_RULES_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)

    def test_creating_a_rule_requires_the_add_permission(self):
        user = grant(self.user, KeywordRule, 'view_keywordrule')
        self.authenticate(user)

        response = self.client.post(
            KEYWORD_RULES_URL,
            {
                'keyword': 'casino',
                'category': 'GAMBLING',
                'severity': 'HIGH',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 403)

    def test_creating_a_keyword_rule(self):
        self.authenticate(self.superuser)

        response = self.client.post(
            KEYWORD_RULES_URL,
            {
                'keyword': ' casino ',
                'category': 'GAMBLING',
                'severity': 'HIGH',
                'description': 'Gambling spam.',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)

        rule = KeywordRule.objects.get(pk=response.data['id'])

        self.assertEqual(rule.keyword, 'casino')
        self.assertEqual(rule.created_by, self.superuser)
        self.assertTrue(rule.is_enabled)

    def test_disabling_a_rule_through_the_api(self):
        rule = factories.keyword_rule('casino')
        self.authenticate(self.superuser)

        response = self.client.patch(
            f'{KEYWORD_RULES_URL}{rule.pk}/',
            {'is_enabled': False},
            format='json',
        )

        rule.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(rule.is_enabled)
        self.assertEqual(rule.updated_by, self.superuser)

    def test_deleting_a_rule_soft_deletes_it(self):
        rule = factories.keyword_rule('casino')
        self.authenticate(self.superuser)

        response = self.client.delete(f'{KEYWORD_RULES_URL}{rule.pk}/')

        rule.refresh_from_db()

        self.assertEqual(response.status_code, 204)
        self.assertIsNotNone(rule.deleted_at)
        self.assertFalse(rule.is_active)
        self.assertEqual(
            self.client.get(KEYWORD_RULES_URL).data['count'],
            0,
        )

    def test_a_domain_rule_rejects_a_url(self):
        self.authenticate(self.superuser)

        response = self.client.post(
            DOMAIN_RULES_URL,
            {
                'domain': 'https://bad.test/path',
                'category': 'SPAM',
                'severity': 'HIGH',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)

    def test_an_html_tag_rule_normalises_the_tag(self):
        self.authenticate(self.superuser)

        response = self.client.post(
            HTML_TAG_RULES_URL,
            {
                'tag': '<SCRIPT>',
                'category': 'INJECTION',
                'severity': 'CRITICAL',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['tag'], 'script')

    def test_filtering_rules_by_category_and_enabled_state(self):
        factories.keyword_rule('casino')
        factories.keyword_rule('poker', is_enabled=False)
        self.authenticate(self.superuser)

        response = self.client.get(
            f'{KEYWORD_RULES_URL}?category=GAMBLING&is_enabled=false'
        )

        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['keyword'], 'poker')

    def test_html_attribute_rule_crud(self):
        self.authenticate(self.superuser)

        response = self.client.post(
            HTML_ATTRIBUTE_RULES_URL,
            {
                'pattern': 'onerror',
                'pattern_type': 'ATTRIBUTE',
                'category': 'INJECTION',
                'severity': 'HIGH',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)

        detail = self.client.get(
            f'{HTML_ATTRIBUTE_RULES_URL}{response.data["id"]}/'
        )

        self.assertEqual(detail.data['pattern'], 'onerror')
        self.assertEqual(detail.data['created_by'], str(self.superuser))


class ProductAndCategoryApiRegressionTests(ContentSecurityApiTestCase):
    """
    The scanner must not change how products and categories behave.
    """

    def test_category_list_is_still_publicly_readable(self):
        factories.category(name='Networking')

        response = self.client.get('/api/v1/categories/')

        self.assertEqual(response.status_code, 200)

    def test_product_list_is_still_publicly_readable(self):
        factories.product(name='Router')

        response = self.client.get('/api/v1/products/')

        self.assertEqual(response.status_code, 200)

    def test_scanning_does_not_alter_the_product_payload(self):
        product = factories.product(
            name='Router',
            description='<script>alert(1)</script> casino',
        )

        scan_object(content_type=ScanContentType.PRODUCT, obj=product)

        response = self.client.get(f'/api/v1/products/{product.pk}/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data['description'],
            '<script>alert(1)</script> casino',
        )
