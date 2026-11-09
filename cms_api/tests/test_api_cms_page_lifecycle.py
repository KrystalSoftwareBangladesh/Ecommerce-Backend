# cms_api/tests/test_api_cms_page_lifecycle.py
"""Page lifecycle tests: publish, unpublish, archive, restore,
dependency-guarded delete, revisions and rollback."""
from django.test import override_settings
from rest_framework.test import APITestCase

from cms_api.models import CmsPage
from cms_api.services.pages import rollback_page
from cms_api.tests import factories


PAGES_URL = '/api/v1/cms/pages/'


def detail_url(page):
    return f'{PAGES_URL}{page.id}/'


def action_url(page, name):
    return f'{detail_url(page)}{name}/'


class CmsPageLifecycleTestCase(APITestCase):
    def setUp(self):
        self.editor = factories.grant(
            factories.user('cms-lifecycle-editor'),
            CmsPage,
            'view_cmspage',
            'add_cmspage',
            'change_cmspage',
        )
        self.publisher = factories.grant(
            factories.user('cms-lifecycle-publisher'),
            CmsPage,
            'view_cmspage',
            'change_cmspage',
            'publish_cms_page',
            'unpublish_cms_page',
            'archive_cms_page',
        )
        self.deleter = factories.grant(
            factories.user('cms-lifecycle-deleter'),
            CmsPage,
            'view_cmspage',
            'delete_cmspage',
        )

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.publisher)


class PublishTests(CmsPageLifecycleTestCase):
    def test_publish_makes_the_page_live(self):
        self.authenticate()
        page = factories.page(self.editor)

        response = self.client.post(
            action_url(page, 'publish'), {}, format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['live'])
        page.refresh_from_db()
        self.assertTrue(page.live)

    def test_publish_requires_the_publish_permission(self):
        self.authenticate(self.editor)
        page = factories.page(self.editor)

        response = self.client.post(
            action_url(page, 'publish'), {}, format='json',
        )

        self.assertEqual(response.status_code, 403)

    def test_publish_named_revision(self):
        self.authenticate()
        page = factories.page(self.editor)
        page.title = 'V2'
        page.save()
        page.save_revision(user=self.editor)

        response = self.client.post(
            action_url(page, 'publish'),
            {'revision_id': page.latest_revision_id},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['live'])


class UnpublishTests(CmsPageLifecycleTestCase):
    def test_unpublish_takes_the_page_offline(self):
        self.authenticate()
        page = factories.page(self.editor)
        self.client.post(
            action_url(page, 'publish'), {}, format='json',
        )

        response = self.client.post(
            action_url(page, 'unpublish'), {}, format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['live'])

    def test_unpublish_requires_the_unpublish_permission(self):
        self.authenticate(self.editor)
        page = factories.page(self.editor)

        response = self.client.post(
            action_url(page, 'unpublish'), {}, format='json',
        )

        self.assertEqual(response.status_code, 403)


class ArchiveTests(CmsPageLifecycleTestCase):
    def test_archive_excludes_the_page_from_the_default_list(self):
        self.authenticate()
        page = factories.page(self.editor, slug='old')

        response = self.client.post(
            action_url(page, 'archive'), {}, format='json',
        )

        self.assertEqual(response.status_code, 200)
        listing = self.client.get(PAGES_URL)
        self.assertEqual(listing.data['count'], 0)

        archived = self.client.get(PAGES_URL, {'archived': 'true'})
        self.assertEqual(archived.data['count'], 1)

    def test_restore_returns_the_page_to_the_default_list(self):
        self.authenticate()
        page = factories.page(self.editor)
        self.client.post(action_url(page, 'archive'), {}, format='json')

        response = self.client.post(
            action_url(page, 'restore'), {}, format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data['archived_at'])
        listing = self.client.get(PAGES_URL)
        self.assertEqual(listing.data['count'], 1)

    def test_archive_requires_the_archive_permission(self):
        self.authenticate(self.editor)
        page = factories.page(self.editor)

        response = self.client.post(
            action_url(page, 'archive'), {}, format='json',
        )

        self.assertEqual(response.status_code, 403)


class DeleteTests(CmsPageLifecycleTestCase):
    def test_delete_requires_the_page_delete_permission(self):
        self.authenticate(self.publisher)
        page = factories.page(self.editor)

        response = self.client.delete(detail_url(page))

        self.assertEqual(response.status_code, 403)

    def test_delete_guarded_page_lists_its_child_page(self):
        self.authenticate(self.deleter)
        page = factories.page(self.editor)
        factories.page(self.editor, slug='child', parent=page)

        response = self.client.delete(detail_url(page))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(response.data['errors']['dependencies']), 1)
        self.assertTrue(
            CmsPage.objects.filter(pk=page.pk).exists()
        )

    def test_delete_acknowledged_page_deletes_its_subtree(self):
        self.authenticate(self.deleter)
        page = factories.page(self.editor)
        factories.page(self.editor, slug='child', parent=page)

        response = self.client.delete(
            detail_url(page) + '?acknowledge=true',
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(CmsPage.objects.filter(pk=page.pk).exists())


class RevisionTests(CmsPageLifecycleTestCase):
    def test_revisions_are_newest_first(self):
        self.authenticate()
        page = factories.page(self.editor)
        page.title = 'V2'
        page.save()
        page.save_revision(user=self.editor)

        response = self.client.get(action_url(page, 'revisions'))

        self.assertEqual(response.status_code, 200)
        ids = [row['id'] for row in response.data]
        self.assertEqual(len(ids), 2)
        self.assertEqual(ids[0], page.latest_revision_id)

    def test_rollback_requires_the_publish_permission(self):
        self.authenticate(self.editor)
        page = factories.page(self.editor)

        response = self.client.post(
            action_url(page, 'rollback'),
            {'revision_id': page.latest_revision_id},
            format='json',
        )

        self.assertEqual(response.status_code, 403)

    def test_rollback_restores_an_old_revision_and_publishes(self):
        self.authenticate()
        page = factories.page(self.editor)
        page.title = 'V2'
        page.save()
        page.save_revision(user=self.editor)
        first = page.revisions.order_by('id').first()

        response = self.client.post(
            action_url(page, 'rollback'),
            {'revision_id': first.id},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        page.refresh_from_db()
        self.assertEqual(page.title, 'Page')
        self.assertTrue(page.live)

    def test_rollback_rejects_a_reserved_prospective_path(self):
        self.authenticate()
        page = factories.page(self.editor, slug='checkout')
        self.client.post(
            action_url(page, 'publish'), {}, format='json',
        )
        first = page.revisions.order_by('id').first()
        page.refresh_from_db()
        page.slug = 'plain'
        page.save()
        page.save_revision(user=self.editor)
        self.client.post(
            action_url(page, 'publish'), {}, format='json',
        )
        page.refresh_from_db()
        live_before = page.live_revision_id

        with override_settings(CMS_RESERVED_PATHS=['/checkout/']):
            response = self.client.post(
                action_url(page, 'rollback'),
                {'revision_id': first.id},
                format='json',
            )

        self.assertEqual(response.status_code, 400)
        page.refresh_from_db()
        self.assertEqual(page.slug, 'plain')
        self.assertEqual(page.url_path, '/plain/')
        self.assertEqual(page.live_revision_id, live_before)
        self.assertEqual(page.live_revision.as_object().slug, 'plain')

    def test_rollback_rejects_a_url_conflict(self):
        self.authenticate()
        mover = factories.page(self.editor, slug='alpha')
        self.client.post(
            action_url(mover, 'publish'), {}, format='json',
        )
        first = mover.revisions.order_by('id').first()
        mover.refresh_from_db()
        mover.slug = 'moved'
        mover.save()
        mover.save_revision(user=self.editor)
        owner = factories.page(self.editor, slug='alpha', title='Alpha')
        self.client.post(
            action_url(owner, 'publish'), {}, format='json',
        )

        response = self.client.post(
            action_url(mover, 'rollback'),
            {'revision_id': first.id},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        mover.refresh_from_db()
        self.assertEqual(mover.slug, 'moved')
        self.assertEqual(mover.url_path, '/moved/')
        self.assertEqual(
            CmsPage.objects.filter(url_path='/alpha/').count(), 1,
        )
        self.assertEqual(
            CmsPage.objects.get(url_path='/alpha/').pk, owner.pk,
        )

    def test_rollback_repaths_a_page_after_an_ancestor_rename(self):
        self.authenticate()
        acme = factories.page(self.editor, slug='acme', title='Acme')
        about = factories.page(
            self.editor, slug='about', title='About', parent=acme,
        )
        team = factories.page(
            self.editor, slug='team', title='Team', parent=about,
        )
        first_about_revision = about.revisions.order_by('id').first()

        acme.refresh_from_db()
        acme.slug = 'acme-corp'
        acme.save()
        acme.save_revision(user=self.editor)

        response = self.client.post(
            action_url(about, 'rollback'),
            {'revision_id': first_about_revision.id},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        about.refresh_from_db()
        team.refresh_from_db()
        self.assertEqual(about.slug, 'about')
        self.assertEqual(about.url_path, '/acme-corp/about/')
        self.assertEqual(team.url_path, '/acme-corp/about/team/')

    def test_rollback_repaths_descendants_with_a_stale_cached_parent(self):
        """A page instance that cached its parent before an ancestor
        rename must still be repathed from the *current* parent.

        ``get_parent()`` (treebeard) caches its result on the
        instance, so a long-lived ``page`` object that outlives an
        ancestor's slug change could otherwise carry a stale parent
        into the rollback even though its own slug is unchanged.
        ``add_child()`` aliases the cache to the exact parent instance
        used at creation time, so the cache is explicitly dropped and
        re-primed here, and the ancestor is renamed through a
        separately-queried instance, to force a genuinely stale
        reference rather than one that would self-update in step with
        the rename."""
        acme = factories.page(self.editor, slug='acme', title='Acme')
        about = factories.page(
            self.editor, slug='about', title='About', parent=acme,
        )
        team = factories.page(
            self.editor, slug='team', title='Team', parent=about,
        )
        first_about_revision_id = about.revisions.order_by(
            'id',
        ).first().id
        del about._cached_parent_obj
        about.get_parent()

        renamer = CmsPage.objects.get(pk=acme.pk)
        renamer.slug = 'acme-corp'
        renamer.save()
        renamer.save_revision(user=self.editor)

        rollback_page(
            page=about, revision_id=first_about_revision_id,
            user=self.editor,
        )

        db_about = CmsPage.objects.get(pk=about.pk)
        db_team = CmsPage.objects.get(pk=team.pk)
        self.assertEqual(db_about.slug, 'about')
        self.assertEqual(db_about.url_path, '/acme-corp/about/')
        self.assertEqual(db_team.url_path, '/acme-corp/about/team/')
