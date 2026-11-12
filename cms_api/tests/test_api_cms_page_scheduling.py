# cms_api/tests/test_api_cms_page_scheduling.py
"""Scheduled publish/unpublish for CMS pages (docs/cms-architecture.md
§12, AD-13).

``go_live_at``/``expire_at`` are accepted only on the publish action,
never on create/update: those run under ``change_cmspage`` alone, and
``expire_at`` is read straight off the live row by the sweep, so
exposing it there would let an editor silently schedule an unpublish
without the ``unpublish_cms_page`` permission.
"""
from datetime import timedelta

from django.utils import timezone

from rest_framework.test import APITestCase

from wagtail.contrib.redirects.models import Redirect
from wagtail.models import Revision

from cms_api.models import CmsPage
from cms_api.services.scheduling import run_scheduled_publishing
from cms_api.tests import factories


PAGES_URL = '/api/v1/cms/pages/'


def action_url(page, name):
    return f'{PAGES_URL}{page.id}/{name}/'


class CmsPageSchedulingTestCase(APITestCase):
    def setUp(self):
        self.editor = factories.grant(
            factories.user('schedule-editor'),
            CmsPage,
            'view_cmspage', 'add_cmspage', 'change_cmspage',
        )
        self.publisher = factories.grant(
            factories.user('schedule-publisher'),
            CmsPage,
            'view_cmspage', 'change_cmspage', 'publish_cms_page',
            'unpublish_cms_page',
        )

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.publisher)


class GoLiveSchedulingTests(CmsPageSchedulingTestCase):
    def test_future_go_live_at_schedules_instead_of_publishing(self):
        self.authenticate()
        page = factories.page(self.editor)
        go_live_at = timezone.now() + timedelta(days=1)

        response = self.client.post(
            action_url(page, 'publish'),
            {'go_live_at': go_live_at.isoformat()},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        page.refresh_from_db()
        self.assertFalse(page.live)
        self.assertEqual(
            page.latest_revision.approved_go_live_at, go_live_at,
        )

    def test_scheduled_sweep_publishes_a_due_revision(self):
        self.authenticate()
        page = factories.page(self.editor)
        self.client.post(
            action_url(page, 'publish'),
            {
                'go_live_at': (
                    timezone.now() + timedelta(days=1)
                ).isoformat(),
            },
            format='json',
        )
        page.refresh_from_db()
        # Simulate real time having passed the originally-scheduled
        # instant: the revision's own ``go_live_at`` (baked into its
        # content at schedule time) and the ``Revision.
        # approved_go_live_at`` the sweep reads are the same moment,
        # so both move into the past together.
        past = timezone.now() - timedelta(minutes=1)
        revision = Revision.objects.get(pk=page.latest_revision_id)
        revision.content['go_live_at'] = past.isoformat()
        revision.approved_go_live_at = past
        revision.save(
            update_fields=['content', 'approved_go_live_at'],
        )

        result = run_scheduled_publishing()

        page.refresh_from_db()
        self.assertTrue(page.live)
        self.assertEqual(result['pages_swept'], 1)

    def test_scheduled_sweep_creates_a_redirect_for_a_moved_slug(self):
        """A page already live gets a slug change scheduled; when the
        sweep makes it live, the same slug-change redirect an explicit
        API publish would create is created (docs §9, §12)."""
        self.authenticate()
        page = factories.page(self.editor, slug='old-slug')
        self.client.post(
            action_url(page, 'publish'), {}, format='json',
        )
        page.refresh_from_db()
        page.slug = 'new-slug'
        page.save()
        past = timezone.now() - timedelta(minutes=1)
        revision = page.save_revision(
            user=self.editor, approved_go_live_at=past,
        )
        revision.content['go_live_at'] = past.isoformat()
        revision.save(update_fields=['content'])

        result = run_scheduled_publishing()

        self.assertEqual(result['redirects_created'], 1)
        self.assertTrue(
            Redirect.objects.filter(old_path='/old-slug').exists()
        )

    def test_revision_id_combined_with_go_live_at_is_rejected(self):
        self.authenticate()
        page = factories.page(self.editor)
        self.client.post(
            action_url(page, 'publish'), {}, format='json',
        )

        response = self.client.post(
            action_url(page, 'publish'),
            {
                'revision_id': page.latest_revision_id,
                'go_live_at': (
                    timezone.now() + timedelta(days=1)
                ).isoformat(),
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)


class ExpirySchedulingTests(CmsPageSchedulingTestCase):
    def test_expire_at_in_the_past_is_rejected(self):
        self.authenticate()
        page = factories.page(self.editor)

        response = self.client.post(
            action_url(page, 'publish'),
            {
                'expire_at': (
                    timezone.now() - timedelta(days=1)
                ).isoformat(),
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)

    def test_expire_at_before_go_live_at_is_rejected(self):
        self.authenticate()
        page = factories.page(self.editor)
        go_live_at = timezone.now() + timedelta(days=2)
        expire_at = timezone.now() + timedelta(days=1)

        response = self.client.post(
            action_url(page, 'publish'),
            {
                'go_live_at': go_live_at.isoformat(),
                'expire_at': expire_at.isoformat(),
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)

    def test_scheduled_sweep_unpublishes_an_expired_page(self):
        self.authenticate()
        page = factories.page(self.editor)
        self.client.post(
            action_url(page, 'publish'),
            {
                'expire_at': (
                    timezone.now() + timedelta(days=1)
                ).isoformat(),
            },
            format='json',
        )
        CmsPage.objects.filter(pk=page.pk).update(
            expire_at=timezone.now() - timedelta(minutes=1),
        )

        run_scheduled_publishing()

        page.refresh_from_db()
        self.assertFalse(page.live)
        self.assertTrue(page.expired)

    def test_plain_republish_clears_a_stale_past_expire_at(self):
        """A revision whose embedded ``expire_at`` has since fallen
        into the past (e.g. because the page already auto-expired
        once) must not carry it back live on a plain republish — or
        the very next sweep would expire the page again immediately.
        """
        self.authenticate()
        page = factories.page(self.editor)
        future_expire_at = timezone.now() + timedelta(days=1)
        self.client.post(
            action_url(page, 'publish'),
            {'expire_at': future_expire_at.isoformat()},
            format='json',
        )
        page.refresh_from_db()
        revision = page.latest_revision
        stale_expire_at = timezone.now() - timedelta(days=1)
        revision.content['expire_at'] = stale_expire_at.isoformat()
        revision.save(update_fields=['content'])

        response = self.client.post(
            action_url(page, 'publish'), {}, format='json',
        )

        self.assertEqual(response.status_code, 200)
        page.refresh_from_db()
        self.assertTrue(page.live)
        self.assertIsNone(page.expire_at)
