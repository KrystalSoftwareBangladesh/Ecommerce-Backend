# cms_api/tests/test_api_cms_redirects.py
"""Slug-change redirects (docs/cms-architecture.md AD-8, §9).

Created only at publish time, never from a draft-only slug edit
(Wagtail's own ``WAGTAILREDIRECTS_AUTO_CREATE`` signal handler is
disabled in settings for exactly this reason); historical paths
collapse directly to the latest canonical URL with no transitive
chains, and a rename back to an earlier slug drops the now-stale
redirect instead of looping.
"""
from rest_framework.test import APITestCase

from wagtail.contrib.redirects.models import Redirect

from cms_api.models import CmsPage
from cms_api.tests import factories


REDIRECTS_URL = '/api/v1/cms/redirects/'
RESOLVE_URL = '/api/v1/cms/redirects/resolve/'
PAGES_URL = '/api/v1/cms/pages/'


def action_url(page, name):
    return f'{PAGES_URL}{page.id}/{name}/'


class CmsRedirectTestCase(APITestCase):
    def setUp(self):
        self.editor = factories.grant(
            factories.user('redirect-editor'),
            CmsPage,
            'view_cmspage', 'add_cmspage', 'change_cmspage',
        )
        self.publisher = factories.grant(
            factories.user('redirect-publisher'),
            CmsPage,
            'view_cmspage', 'change_cmspage', 'publish_cms_page',
        )
        self.deleter = factories.grant(
            factories.user('redirect-deleter'),
            CmsPage,
            'view_cmspage', 'delete_cmspage',
        )

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.publisher)

    def publish_page(self, page):
        self.authenticate()
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(action_url(page, 'publish'), {})


class SlugChangeRedirectTests(CmsRedirectTestCase):
    def test_publish_with_changed_slug_creates_a_redirect(self):
        page = factories.page(self.editor, slug='old-slug')
        self.publish_page(page)
        page.refresh_from_db()
        page.slug = 'new-slug'
        page.save()
        page.save_revision(user=self.editor)

        response = self.publish_page(page)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Redirect.objects.filter(old_path='/old-slug').exists()
        )

    def test_draft_slug_edit_creates_no_redirect(self):
        """Wagtail's own slug-change signal still fires (it fires on
        every ``Page.save()`` with a changed slug); the handler that
        would otherwise turn it into a redirect is disabled, so a
        draft-only edit (never published) must leave no row behind.
        """
        page = factories.page(self.editor, slug='old-slug')
        self.publish_page(page)
        page.refresh_from_db()

        with self.captureOnCommitCallbacks(execute=True):
            page.slug = 'draft-only'
            page.save()
            page.save_revision(user=self.editor)

        self.assertFalse(Redirect.objects.exists())

    def test_resolve_returns_the_current_published_path(self):
        page = factories.page(self.editor, slug='old-slug')
        self.publish_page(page)
        page.refresh_from_db()
        page.slug = 'new-slug'
        page.save()
        page.save_revision(user=self.editor)
        self.publish_page(page)

        response = self.client.get(
            RESOLVE_URL, {'path': '/old-slug/'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['path'], '/new-slug/')

    def test_resolve_returns_404_for_an_unknown_path(self):
        response = self.client.get(
            RESOLVE_URL, {'path': '/never-existed/'},
        )

        self.assertEqual(response.status_code, 404)

    def test_resolve_is_public(self):
        """No authentication is set up here at all."""
        response = self.client.get(
            RESOLVE_URL, {'path': '/never-existed/'},
        )

        self.assertNotEqual(response.status_code, 403)

    def test_resolve_requires_a_path_query_param(self):
        response = self.client.get(RESOLVE_URL)

        self.assertEqual(response.status_code, 400)

    def test_rename_back_to_the_original_slug_drops_the_stale_redirect(
        self,
    ):
        page = factories.page(self.editor, slug='alpha')
        self.publish_page(page)
        page.refresh_from_db()
        page.slug = 'beta'
        page.save()
        page.save_revision(user=self.editor)
        self.publish_page(page)
        self.assertTrue(
            Redirect.objects.filter(old_path='/alpha').exists()
        )
        page.refresh_from_db()
        page.slug = 'alpha'
        page.save()
        page.save_revision(user=self.editor)

        response = self.publish_page(page)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Redirect.objects.filter(old_path='/alpha').exists()
        )
        resolve_beta = self.client.get(
            RESOLVE_URL, {'path': '/beta/'},
        )
        self.assertEqual(resolve_beta.status_code, 200)
        self.assertEqual(resolve_beta.data['path'], '/alpha/')

    def test_redirect_propagates_to_live_descendants_on_parent_rename(
        self,
    ):
        parent = factories.page(self.editor, slug='parent')
        child = factories.page(
            self.editor, slug='child', parent=parent,
        )
        self.publish_page(parent)
        self.publish_page(child)
        parent.refresh_from_db()
        parent.slug = 'renamed-parent'
        parent.save()
        parent.save_revision(user=self.editor)

        response = self.publish_page(parent)

        self.assertEqual(response.status_code, 200)
        resolved = self.client.get(
            RESOLVE_URL, {'path': '/parent/child/'},
        )
        self.assertEqual(resolved.status_code, 200)
        self.assertEqual(
            resolved.data['path'], '/renamed-parent/child/',
        )


class RedirectDeleteGuardTests(CmsRedirectTestCase):
    def test_existing_redirect_does_not_block_page_deletion(self):
        """``Redirect`` is not registered with Wagtail's
        ``ReferenceIndex``, so a redirect pointing at a page is not a
        dependency the delete guard (``delete_page``) lists — it is
        not a reference tracked the way a ``CmsPageSection`` or a
        StreamField chooser is."""
        page = factories.page(self.editor, slug='old-slug')
        self.publish_page(page)
        page.refresh_from_db()
        page.slug = 'new-slug'
        page.save()
        page.save_revision(user=self.editor)
        self.publish_page(page)
        self.assertTrue(Redirect.objects.exists())

        self.client.force_authenticate(user=self.deleter)
        response = self.client.delete(f'{PAGES_URL}{page.id}/')

        self.assertEqual(response.status_code, 204)


class CmsRedirectManagementTests(CmsRedirectTestCase):
    def test_list_requires_authentication(self):
        response = self.client.get(REDIRECTS_URL)

        self.assertEqual(response.status_code, 401)

    def test_list_requires_the_view_page_permission(self):
        unprivileged = factories.user('redirect-no-perm')
        self.client.force_authenticate(user=unprivileged)

        response = self.client.get(REDIRECTS_URL)

        self.assertEqual(response.status_code, 403)

    def test_list_shows_created_redirects(self):
        page = factories.page(self.editor, slug='old-slug')
        self.publish_page(page)
        page.refresh_from_db()
        page.slug = 'new-slug'
        page.save()
        page.save_revision(user=self.editor)
        self.publish_page(page)

        self.authenticate()
        response = self.client.get(REDIRECTS_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(
            response.data['results'][0]['current_path'], '/new-slug/',
        )
