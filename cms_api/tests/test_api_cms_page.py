# cms_api/tests/test_api_cms_page.py
"""CmsPage API tests: CRUD from templates, reserved paths,
composition writes and optimistic locking."""
from rest_framework.test import APITestCase

from cms_api.models import CmsPage, CmsPageSection
from cms_api.pages.templates import PAGE_TEMPLATES
from cms_api.tests import factories


PAGES_URL = '/api/v1/cms/pages/'


def detail_url(page):
    return f'{PAGES_URL}{page.id}/'


def action_url(page, name):
    return f'{detail_url(page)}{name}/'


class CmsPageTestCase(APITestCase):
    def setUp(self):
        self.editor = factories.grant(
            factories.user('cms-page-editor'),
            CmsPage,
            'view_cmspage',
            'add_cmspage',
            'change_cmspage',
        )

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.editor)


class CreatePageTests(CmsPageTestCase):
    def test_create_seeds_composition_from_template(self):
        self.authenticate()
        response = self.client.post(
            PAGES_URL,
            {'title': 'About us', 'slug': 'landing-demo',
             'template_key': 'landing'},
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        expected = len(PAGE_TEMPLATES['landing']['sections'])
        self.assertEqual(len(response.data['sections']), expected)
        page = CmsPage.objects.get(slug='landing-demo')
        self.assertFalse(page.live)

    def test_create_accepts_explicit_sections(self):
        self.authenticate()
        response = self.client.post(
            PAGES_URL,
            {'title': 'Custom', 'slug': 'custom',
             'sections': [factories.page_row(name='Hero')]},
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.data['sections']), 1)
        self.assertEqual(response.data['sections'][0]['name'], 'Hero')

    def test_create_rejects_template_and_sections_together(self):
        self.authenticate()
        response = self.client.post(
            PAGES_URL,
            {'title': 'Both', 'slug': 'both',
             'template_key': 'landing',
             'sections': [factories.page_row()]},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('sections', response.data['errors'])

    def test_create_rejects_reserved_path(self):
        self.authenticate()
        response = self.client.post(
            PAGES_URL,
            {'title': 'API', 'slug': 'api'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('slug', response.data['errors'])


class UpdatePageTests(CmsPageTestCase):
    def test_update_replaces_composition(self):
        self.authenticate()
        page = factories.page(self.editor)
        factories.page_section(page, self.editor)

        response = self.client.patch(
            detail_url(page),
            {'sections': [factories.page_row(name='New')]},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['sections']), 1)
        self.assertEqual(response.data['sections'][0]['name'], 'New')

    def test_update_slug_to_reserved_path_is_rejected(self):
        self.authenticate()
        page = factories.page(self.editor)

        response = self.client.patch(
            detail_url(page), {'slug': 'admin'}, format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('slug', response.data['errors'])

    def test_stale_base_revision_conflicts(self):
        self.authenticate()
        page = factories.page(self.editor)

        response = self.client.patch(
            detail_url(page),
            {'title': 'Changed', 'base_revision_id': 999999},
            format='json',
        )

        self.assertEqual(response.status_code, 409)

    def test_current_base_revision_updates(self):
        self.authenticate()
        page = factories.page(self.editor)

        response = self.client.patch(
            detail_url(page),
            {'title': 'Changed',
             'base_revision_id': page.latest_revision_id},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['title'], 'Changed')


class CompositionTests(CmsPageTestCase):
    def test_add_row(self):
        self.authenticate()
        page = factories.page(self.editor)

        response = self.client.post(
            action_url(page, 'sections'),
            {'name': 'Hero', 'content': factories.hero_content()},
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['name'], 'Hero')

    def test_add_row_requires_exactly_one_source(self):
        self.authenticate()
        page = factories.page(self.editor)

        response = self.client.post(
            action_url(page, 'sections'), {}, format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('content', response.data['errors'])

    def test_add_global_row(self):
        self.authenticate()
        page = factories.page(self.editor)
        shared = factories.section(user=self.editor)

        response = self.client.post(
            action_url(page, 'sections'),
            {'name': 'Shared', 'global_section': shared.pk},
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['global_section'], shared.pk)

    def test_update_row_switches_global_to_local(self):
        self.authenticate()
        page = factories.page(self.editor)
        shared = factories.section(user=self.editor)
        row = factories.page_section(
            page, self.editor, global_section=shared.pk,
        )

        response = self.client.patch(
            action_url(page, 'sections') + f'{row.id}/',
            {'global_section': None,
             'content': factories.hero_content('Mine')},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data['global_section'])
        row.refresh_from_db()
        self.assertIsNone(row.global_section)

    def test_remove_row(self):
        self.authenticate()
        page = factories.page(self.editor)
        row = factories.page_section(page, self.editor)

        response = self.client.delete(
            action_url(page, 'sections') + f'{row.id}/',
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(page.sections.count(), 0)

    def test_reorder_rows(self):
        self.authenticate()
        page = factories.page(self.editor)
        first = factories.page_section(page, self.editor, name='A')
        second = factories.page_section(page, self.editor, name='B')

        response = self.client.put(
            action_url(page, 'sections') + 'reorder/',
            {'order': [second.id, first.id]},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        # Assert persisted DB order (rows may be cached in-memory).
        rows = list(
            CmsPageSection.objects.filter(page=page)
            .order_by('sort_order')
        )
        self.assertEqual(rows[0].id, second.id)
        self.assertEqual(rows[1].id, first.id)

    def test_reorder_rejects_incomplete_order(self):
        self.authenticate()
        page = factories.page(self.editor)
        row = factories.page_section(page, self.editor)
        factories.page_section(page, self.editor)

        response = self.client.put(
            action_url(page, 'sections') + 'reorder/',
            {'order': [row.id]},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('order', response.data['errors'])

    def test_duplicate_row(self):
        self.authenticate()
        page = factories.page(self.editor)
        row = factories.page_section(page, self.editor, name='A')

        response = self.client.post(
            action_url(page, 'sections') + f'{row.id}/duplicate/',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(page.sections.count(), 2)
