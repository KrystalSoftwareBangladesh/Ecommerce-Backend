# cms_api/tests/test_api_cms_section.py
"""CRUD and input-validation tests for the CMS section API."""
from rest_framework.test import APITestCase

from cms_api.models import CmsSection
from cms_api.tests import factories


SECTIONS_URL = '/api/v1/cms/sections/'


def detail_url(section):
    return f'{SECTIONS_URL}{section.id}/'


class CmsSectionApiTestCase(APITestCase):
    def setUp(self):
        self.editor = factories.grant(
            factories.user('cms-editor'),
            CmsSection,
            'view_cmssection',
            'add_cmssection',
            'change_cmssection',
        )
        self.publisher = factories.grant(
            factories.user('cms-publisher'),
            CmsSection,
            'view_cmssection',
            'publish_cms_section',
            'unpublish_cms_section',
            'archive_cms_section',
        )
        self.deleter = factories.grant(
            factories.user('cms-deleter'),
            CmsSection,
            'view_cmssection',
            'delete_cmssection',
        )
        self.outsider = factories.user('cms-outsider')

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.editor)


class CmsSectionCrudTests(CmsSectionApiTestCase):
    def test_list_requires_authentication(self):
        response = self.client.get(SECTIONS_URL)

        self.assertEqual(response.status_code, 401)

    def test_list_requires_the_view_permission(self):
        self.authenticate(self.outsider)

        response = self.client.get(SECTIONS_URL)

        self.assertEqual(response.status_code, 403)

    def test_create_returns_a_draft(self):
        self.authenticate()

        response = self.client.post(
            SECTIONS_URL,
            {
                'name': 'Home hero',
                'section_type': 'hero_banner',
                'content': factories.hero_content('Hello'),
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['name'], 'Home hero')
        self.assertFalse(response.data['live'])
        self.assertEqual(
            response.data['content'][0]['type'],
            'hero_banner',
        )
        self.assertEqual(
            response.data['content'][0]['value']['heading'],
            'Hello',
        )

    def test_create_requires_the_add_permission(self):
        self.authenticate(self.outsider)

        response = self.client.post(
            SECTIONS_URL,
            {
                'name': 'Nope',
                'section_type': 'hero_banner',
                'content': factories.hero_content(),
            },
            format='json',
        )

        self.assertEqual(response.status_code, 403)

    def test_create_rejects_content_type_mismatch(self):
        self.authenticate()

        response = self.client.post(
            SECTIONS_URL,
            {
                'name': 'Bad',
                'section_type': 'faq',
                'content': factories.hero_content(),
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('content', response.data['errors'])

    def test_create_rejects_multiple_blocks(self):
        self.authenticate()

        response = self.client.post(
            SECTIONS_URL,
            {
                'name': 'Bad',
                'section_type': 'hero_banner',
                'content': (
                    factories.hero_content()
                    + factories.hero_content('Second')
                ),
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)

    def test_create_rejects_unknown_block_type(self):
        self.authenticate()

        response = self.client.post(
            SECTIONS_URL,
            {
                'name': 'Bad',
                'section_type': 'hero_banner',
                'content': [{'type': 'nope', 'value': {}}],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)

    def test_create_rejects_invalid_mode_combination(self):
        """MANUAL product_collection without products fails."""
        self.authenticate()

        response = self.client.post(
            SECTIONS_URL,
            {
                'name': 'Picks',
                'section_type': 'product_collection',
                'content': [{
                    'type': 'product_collection',
                    'value': {
                        'mode': 'MANUAL',
                        'products': [],
                        'category': None,
                        'brand': None,
                        'limit': 8,
                    },
                }],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('content', response.data['errors'])

    def test_update_changes_name_and_content(self):
        self.authenticate()
        section = factories.section()

        response = self.client.patch(
            detail_url(section),
            {'name': 'Renamed', 'content': factories.hero_content('New')},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], 'Renamed')
        self.assertEqual(
            response.data['content'][0]['value']['heading'],
            'New',
        )

    def test_update_ignores_section_type(self):
        """section_type is immutable after creation."""
        self.authenticate()
        section = factories.section()

        response = self.client.patch(
            detail_url(section),
            {'section_type': 'faq'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['section_type'], 'hero_banner')

    def test_update_with_current_base_revision_id_succeeds(self):
        self.authenticate()
        section = factories.section(user=self.editor)

        response = self.client.patch(
            detail_url(section),
            {
                'name': 'Renamed',
                'base_revision_id': section.latest_revision_id,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)

    def test_update_with_stale_base_revision_id_conflicts(self):
        self.authenticate()
        section = factories.section(user=self.editor)
        stale_revision_id = section.latest_revision_id
        self.client.patch(
            detail_url(section),
            {'name': 'First edit'},
            format='json',
        )

        response = self.client.patch(
            detail_url(section),
            {
                'name': 'Second edit',
                'base_revision_id': stale_revision_id,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 409)

    def test_detail_hides_soft_deleted_sections(self):
        self.authenticate()
        section = factories.section()
        section.soft_delete()

        response = self.client.get(detail_url(section))

        self.assertEqual(response.status_code, 404)
