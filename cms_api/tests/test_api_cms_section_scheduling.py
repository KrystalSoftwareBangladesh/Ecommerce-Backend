# cms_api/tests/test_api_cms_section_scheduling.py
"""Scheduled publish/unpublish for CMS sections (docs/cms-architecture.md
§12, AD-13)."""
from datetime import timedelta

from django.utils import timezone

from rest_framework.test import APITestCase

from wagtail.models import Revision

from cms_api.models import CmsSection
from cms_api.services.scheduling import run_scheduled_publishing
from cms_api.tests import factories


SECTIONS_URL = '/api/v1/cms/sections/'


def action_url(section, name):
    return f'{SECTIONS_URL}{section.id}/{name}/'


class CmsSectionSchedulingTestCase(APITestCase):
    def setUp(self):
        self.editor = factories.grant(
            factories.user('section-schedule-editor'),
            CmsSection,
            'view_cmssection', 'add_cmssection', 'change_cmssection',
        )
        self.publisher = factories.grant(
            factories.user('section-schedule-publisher'),
            CmsSection,
            'view_cmssection', 'change_cmssection',
            'publish_cms_section',
        )

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.publisher)


class GoLiveSchedulingTests(CmsSectionSchedulingTestCase):
    def test_future_go_live_at_schedules_instead_of_publishing(self):
        self.authenticate()
        section = factories.section(user=self.editor)
        go_live_at = timezone.now() + timedelta(days=1)

        response = self.client.post(
            action_url(section, 'publish'),
            {'go_live_at': go_live_at.isoformat()},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        section.refresh_from_db()
        self.assertFalse(section.live)
        self.assertEqual(
            section.latest_revision.approved_go_live_at, go_live_at,
        )

    def test_scheduled_sweep_publishes_a_due_revision(self):
        self.authenticate()
        section = factories.section(user=self.editor)
        self.client.post(
            action_url(section, 'publish'),
            {
                'go_live_at': (
                    timezone.now() + timedelta(days=1)
                ).isoformat(),
            },
            format='json',
        )
        section.refresh_from_db()
        past = timezone.now() - timedelta(minutes=1)
        revision = Revision.objects.get(pk=section.latest_revision_id)
        revision.content['go_live_at'] = past.isoformat()
        revision.approved_go_live_at = past
        revision.save(
            update_fields=['content', 'approved_go_live_at'],
        )

        run_scheduled_publishing()

        section.refresh_from_db()
        self.assertTrue(section.live)

    def test_revision_id_combined_with_go_live_at_is_rejected(self):
        self.authenticate()
        section = factories.section(user=self.editor)
        self.client.post(
            action_url(section, 'publish'), {}, format='json',
        )

        response = self.client.post(
            action_url(section, 'publish'),
            {
                'revision_id': section.latest_revision_id,
                'go_live_at': (
                    timezone.now() + timedelta(days=1)
                ).isoformat(),
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)


class ExpirySchedulingTests(CmsSectionSchedulingTestCase):
    def test_expire_at_in_the_past_is_rejected(self):
        self.authenticate()
        section = factories.section(user=self.editor)

        response = self.client.post(
            action_url(section, 'publish'),
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
        section = factories.section(user=self.editor)

        response = self.client.post(
            action_url(section, 'publish'),
            {
                'go_live_at': (
                    timezone.now() + timedelta(days=2)
                ).isoformat(),
                'expire_at': (
                    timezone.now() + timedelta(days=1)
                ).isoformat(),
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)

    def test_scheduled_sweep_unpublishes_an_expired_section(self):
        self.authenticate()
        section = factories.section(user=self.editor)
        self.client.post(
            action_url(section, 'publish'),
            {
                'expire_at': (
                    timezone.now() + timedelta(days=1)
                ).isoformat(),
            },
            format='json',
        )
        CmsSection.objects.filter(pk=section.pk).update(
            expire_at=timezone.now() - timedelta(minutes=1),
        )

        run_scheduled_publishing()

        section.refresh_from_db()
        self.assertFalse(section.live)
        self.assertTrue(section.expired)

    def test_plain_republish_clears_a_stale_past_expire_at(self):
        self.authenticate()
        section = factories.section(user=self.editor)
        future_expire_at = timezone.now() + timedelta(days=1)
        self.client.post(
            action_url(section, 'publish'),
            {'expire_at': future_expire_at.isoformat()},
            format='json',
        )
        section.refresh_from_db()
        revision = Revision.objects.get(pk=section.latest_revision_id)
        stale_expire_at = timezone.now() - timedelta(days=1)
        revision.content['expire_at'] = stale_expire_at.isoformat()
        revision.save(update_fields=['content'])

        response = self.client.post(
            action_url(section, 'publish'), {}, format='json',
        )

        self.assertEqual(response.status_code, 200)
        section.refresh_from_db()
        self.assertTrue(section.live)
        self.assertIsNone(section.expire_at)
