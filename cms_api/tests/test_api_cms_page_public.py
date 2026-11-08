# cms_api/tests/test_api_cms_page_public.py
"""Public page API tests: published-only reads (draft isolation)."""
from rest_framework.test import APITestCase

from cms_api.services import (
    archive_page,
    publish_page,
    publish_section,
)
from cms_api.tests import factories


PUBLIC_URL = '/api/v1/cms/public/pages/'


class CmsPagePublicTestCase(APITestCase):
    def setUp(self):
        self.owner = factories.user('cms-public-owner')

    def published_page(self, slug='about', **kwargs):
        page = factories.page(self.owner, slug=slug, **kwargs)
        publish_page(page=page, user=self.owner)
        return page

    def get_page(self, path):
        return self.client.get(PUBLIC_URL, {'path': path})


class PublicDetailTests(CmsPagePublicTestCase):
    def test_published_page_resolves_its_path(self):
        page = self.published_page(title='About us')

        response = self.get_page(page.url_path)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['title'], 'About us')
        self.assertEqual(response.data['path'], page.url_path)

    def test_unpublished_page_is_not_served(self):
        page = factories.page(self.owner, slug='draft')

        response = self.get_page(page.url_path)

        self.assertEqual(response.status_code, 404)

    def test_archived_page_is_not_served(self):
        page = self.published_page(slug='old')
        archive_page(page=page, user=self.owner)

        response = self.get_page(page.url_path)

        self.assertEqual(response.status_code, 404)

    def test_unknown_path_is_not_found(self):
        response = self.get_page('/missing/')

        self.assertEqual(response.status_code, 404)

    def test_draft_changes_are_not_served(self):
        page = self.published_page(title='Published')
        page.refresh_from_db()
        page.title = 'Draft title'
        page.save()
        page.save_revision(user=self.owner)

        response = self.get_page(page.url_path)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['title'], 'Published')

    def test_draft_slug_path_is_not_served(self):
        page = self.published_page(slug='about', title='About us')
        page.refresh_from_db()
        page.slug = 'about-v2'
        page.save()
        page.save_revision(user=self.owner)
        page.refresh_from_db()
        self.assertEqual(page.url_path, '/about-v2/')

        response = self.get_page('/about-v2/')

        self.assertEqual(response.status_code, 404)

    def test_published_path_resolves_after_a_draft_slug_change(self):
        page = self.published_page(slug='about', title='About us')
        page.refresh_from_db()
        page.slug = 'about-v2'
        page.save()
        page.save_revision(user=self.owner)

        response = self.get_page('/about/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['slug'], 'about')
        self.assertEqual(response.data['path'], '/about/')


class PublicListTests(CmsPagePublicTestCase):
    def test_list_includes_only_published_pages(self):
        page = self.published_page(slug='about')
        factories.page(self.owner, slug='draft')

        response = self.client.get(PUBLIC_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['path'], page.url_path)

    def test_list_needs_no_authentication(self):
        self.published_page(slug='about')

        response = self.client.get(PUBLIC_URL)

        self.assertEqual(response.status_code, 200)

    def test_list_reports_published_urls_after_a_draft_slug_change(self):
        page = self.published_page(slug='about', title='About us')
        page.refresh_from_db()
        page.slug = 'about-v2'
        page.save()
        page.save_revision(user=self.owner)

        response = self.client.get(PUBLIC_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['slug'], 'about')
        self.assertEqual(response.data[0]['path'], '/about/')


class PublicCompositionTests(CmsPagePublicTestCase):
    def test_local_rows_are_served(self):
        page = factories.page(self.owner, slug='compose')
        factories.page_section(
            page, self.owner, name='Hero',
            content=factories.hero_content('Welcome'),
        )
        publish_page(page=page, user=self.owner)

        response = self.get_page(page.url_path)

        self.assertEqual(response.status_code, 200)
        rows = response.data['sections']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['name'], 'Hero')
        self.assertEqual(rows[0]['source'], 'local')
        self.assertEqual(
            rows[0]['content'][0]['value']['heading'],
            'Welcome',
        )

    def test_unpublished_global_rows_are_omitted(self):
        shared = factories.section(
            name='Shared', user=self.owner, live=False,
        )
        page = factories.page(self.owner, slug='compose')
        factories.page_section(
            page, self.owner, name='Shared row',
            global_section=shared.pk,
        )
        factories.page_section(page, self.owner, name='Local row')
        publish_page(page=page, user=self.owner)

        response = self.get_page(page.url_path)

        rows = response.data['sections']
        self.assertEqual([row['name'] for row in rows], ['Local row'])

    def test_global_rows_resolve_to_published_content(self):
        shared = factories.section(
            name='Shared',
            content=factories.hero_content('Shared hero'),
            user=self.owner,
        )
        publish_section(section=shared, user=self.owner)
        page = factories.page(self.owner, slug='compose')
        factories.page_section(
            page, self.owner, name='Shared row',
            global_section=shared.pk,
        )
        publish_page(page=page, user=self.owner)

        response = self.get_page(page.url_path)

        rows = response.data['sections']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['source'], 'global')
        self.assertEqual(rows[0]['global_section'], shared.pk)
        self.assertEqual(
            rows[0]['content'][0]['value']['heading'],
            'Shared hero',
        )
