# cms_api/tests/test_api_cms_sitemap.py
"""Public sitemap endpoint (docs/cms-architecture.md §6, §9)."""
from rest_framework.test import APITestCase

from cms_api.models import CmsPage
from cms_api.tests import factories


SITEMAP_URL = '/api/v1/cms/public/sitemap/'
PAGES_URL = '/api/v1/cms/pages/'


def action_url(page, name):
    return f'{PAGES_URL}{page.id}/{name}/'


class CmsSitemapTestCase(APITestCase):
    def setUp(self):
        self.editor = factories.grant(
            factories.user('sitemap-editor'),
            CmsPage,
            'view_cmspage', 'add_cmspage', 'change_cmspage',
            'publish_cms_page', 'archive_cms_page',
        )

    def authenticate(self):
        self.client.force_authenticate(user=self.editor)

    def publish(self, page):
        self.authenticate()
        return self.client.post(action_url(page, 'publish'), {})


class SitemapFilteringTests(CmsSitemapTestCase):
    def test_lists_only_published_pages(self):
        live = factories.page(self.editor, slug='live')
        factories.page(self.editor, slug='draft')
        self.publish(live)

        response = self.client.get(SITEMAP_URL)

        self.assertEqual(response.status_code, 200)
        paths = [row['path'] for row in response.data]
        self.assertEqual(paths, ['/live/'])

    def test_excludes_an_archived_page(self):
        page = factories.page(self.editor, slug='archived')
        self.publish(page)
        self.client.post(action_url(page, 'archive'), {})

        response = self.client.get(SITEMAP_URL)

        self.assertEqual(response.data, [])

    def test_excludes_a_noindex_page_using_the_published_value(self):
        """``seo_noindex`` is filtered from the published snapshot,
        not the row: a draft edit writes the field straight to the
        row before any publish (the same draft-isolation issue Phase
        2 fixed for paths)."""
        page = factories.page(self.editor, slug='noindex-page')
        self.publish(page)
        page.refresh_from_db()
        page.seo_noindex = True
        page.save()
        page.save_revision(user=self.editor)
        # Draft-only change: still published with seo_noindex=False.

        response = self.client.get(SITEMAP_URL)

        paths = [row['path'] for row in response.data]
        self.assertEqual(paths, ['/noindex-page/'])
        self.assertFalse(response.data[0]['seo_noindex'])

    def test_includes_a_page_once_its_noindex_change_is_published(self):
        page = factories.page(self.editor, slug='now-noindexed')
        self.publish(page)
        page.refresh_from_db()
        page.seo_noindex = True
        page.save()
        page.save_revision(user=self.editor)
        self.publish(page)

        response = self.client.get(SITEMAP_URL)

        self.assertEqual(response.data, [])

    def test_is_public(self):
        response = self.client.get(SITEMAP_URL)

        self.assertNotEqual(response.status_code, 401)
        self.assertNotEqual(response.status_code, 403)
