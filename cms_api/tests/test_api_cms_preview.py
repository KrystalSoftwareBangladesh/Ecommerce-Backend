# cms_api/tests/test_api_cms_preview.py
"""Signed preview tokens (docs/cms-architecture.md §5.7, AD-15)."""
from django.core import signing

from rest_framework.test import APITestCase

from cms_api.models import CmsPage, CmsSection
from cms_api.services.preview import PREVIEW_SALT
from cms_api.tests import factories


PAGES_URL = '/api/v1/cms/pages/'
SECTIONS_URL = '/api/v1/cms/sections/'


def preview_token_url(resource_url, obj):
    return f'{resource_url}{obj.id}/preview-token/'


def preview_url(token):
    return f'/api/v1/cms/public/preview/{token}/'


class CmsPreviewTestCase(APITestCase):
    def setUp(self):
        self.editor = factories.grant(
            factories.user('preview-editor'),
            CmsPage,
            'view_cmspage', 'add_cmspage', 'change_cmspage',
        )
        factories.grant(
            self.editor, CmsSection,
            'view_cmssection', 'add_cmssection', 'change_cmssection',
        )
        self.stranger = factories.user('preview-stranger')

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.editor)


class PagePreviewTests(CmsPreviewTestCase):
    def test_issuing_a_token_requires_change_permission(self):
        self.client.force_authenticate(user=self.stranger)
        page = factories.page(self.editor)

        response = self.client.post(
            preview_token_url(PAGES_URL, page), {}, format='json',
        )

        self.assertEqual(response.status_code, 403)

    def test_token_resolves_to_draft_content(self):
        self.authenticate()
        page = factories.page(self.editor, title='Draft title')

        issued = self.client.post(
            preview_token_url(PAGES_URL, page), {}, format='json',
        )
        self.assertEqual(issued.status_code, 200)
        token = issued.data['token']

        response = self.client.get(preview_url(token))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['title'], 'Draft title')
        self.assertEqual(
            response['Cache-Control'], 'no-store',
        )

    def test_preview_is_public_given_a_valid_token(self):
        self.authenticate()
        page = factories.page(self.editor)
        issued = self.client.post(
            preview_token_url(PAGES_URL, page), {}, format='json',
        )
        token = issued.data['token']
        self.client.force_authenticate(user=None)

        response = self.client.get(preview_url(token))

        self.assertEqual(response.status_code, 200)

    def test_invalid_token_returns_404(self):
        response = self.client.get(preview_url('not-a-real-token'))

        self.assertEqual(response.status_code, 404)

    def test_tampered_token_returns_404(self):
        self.authenticate()
        page = factories.page(self.editor)
        issued = self.client.post(
            preview_token_url(PAGES_URL, page), {}, format='json',
        )
        token = issued.data['token']

        response = self.client.get(preview_url(token + 'x'))

        self.assertEqual(response.status_code, 404)

    def test_resolving_checks_the_user_still_has_permission(self):
        self.authenticate()
        page = factories.page(self.editor)
        issued = self.client.post(
            preview_token_url(PAGES_URL, page), {}, format='json',
        )
        token = issued.data['token']
        self.editor.user_permissions.clear()

        response = self.client.get(preview_url(token))

        self.assertEqual(response.status_code, 403)

    def test_token_is_bound_to_the_revision_it_was_issued_for(self):
        self.authenticate()
        page = factories.page(self.editor, title='V1')
        first = self.client.post(
            preview_token_url(PAGES_URL, page), {}, format='json',
        )
        token = first.data['token']
        page.title = 'V2'
        page.save()
        page.save_revision(user=self.editor)

        response = self.client.get(preview_url(token))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['title'], 'V1')

    def test_token_without_a_revision_is_rejected(self):
        self.authenticate()
        token = signing.dumps(
            {
                'kind': 'page', 'object_id': 999999,
                'revision_id': 999999, 'user_id': self.editor.id,
            },
            salt=PREVIEW_SALT, compress=False,
        )

        response = self.client.get(preview_url(token))

        self.assertEqual(response.status_code, 404)


class SectionPreviewTests(CmsPreviewTestCase):
    def test_token_resolves_to_draft_content(self):
        self.authenticate()
        section = factories.section(
            name='Draft hero', user=self.editor,
        )

        issued = self.client.post(
            preview_token_url(SECTIONS_URL, section),
            {}, format='json',
        )
        self.assertEqual(issued.status_code, 200)

        response = self.client.get(preview_url(issued.data['token']))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], 'Draft hero')

    def test_issuing_a_token_requires_change_permission(self):
        self.client.force_authenticate(user=self.stranger)
        section = factories.section(user=self.editor)

        response = self.client.post(
            preview_token_url(SECTIONS_URL, section),
            {}, format='json',
        )

        self.assertEqual(response.status_code, 403)
