# cms_api/tests/test_api_cms_section_lifecycle.py
"""Lifecycle tests: publish, unpublish, archive, delete guard,
revisions and rollback."""
from rest_framework.test import APITestCase

from cms_api.models import CmsSection
from cms_api.tests import factories


SECTIONS_URL = '/api/v1/cms/sections/'


def detail_url(section):
    return f'{SECTIONS_URL}{section.id}/'


def action_url(section, name):
    return f'{detail_url(section)}{name}/'


class CmsSectionLifecycleTestCase(APITestCase):
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
            'change_cmssection',
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

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.publisher)


class PublishTests(CmsSectionLifecycleTestCase):
    def test_publish_makes_the_section_live(self):
        self.authenticate()
        section = factories.section(user=self.editor)

        response = self.client.post(
            action_url(section, 'publish'), {}, format='json'
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['live'])
        section.refresh_from_db()
        self.assertTrue(section.live)

    def test_publish_requires_the_publish_permission(self):
        self.authenticate(self.editor)
        section = factories.section(user=self.editor)

        response = self.client.post(
            action_url(section, 'publish'), {}, format='json'
        )

        self.assertEqual(response.status_code, 403)

    def test_publish_without_a_revision_is_rejected(self):
        self.authenticate()
        section = factories.section()

        response = self.client.post(
            action_url(section, 'publish'), {}, format='json'
        )

        self.assertEqual(response.status_code, 400)


class UnpublishTests(CmsSectionLifecycleTestCase):
    def test_unpublish_hides_the_section(self):
        self.authenticate()
        section = factories.section(user=self.editor, live=True)

        response = self.client.post(
            action_url(section, 'unpublish'), {}, format='json'
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['live'])

    def test_unpublish_requires_the_unpublish_permission(self):
        self.authenticate(self.editor)
        section = factories.section(user=self.editor, live=True)

        response = self.client.post(
            action_url(section, 'unpublish'), {}, format='json'
        )

        self.assertEqual(response.status_code, 403)

    def test_unpublish_a_draft_is_rejected(self):
        self.authenticate()
        section = factories.section(user=self.editor, live=False)

        response = self.client.post(
            action_url(section, 'unpublish'), {}, format='json'
        )

        self.assertEqual(response.status_code, 400)


class ArchiveTests(CmsSectionLifecycleTestCase):
    def test_archive_excludes_the_section_from_the_default_list(self):
        self.authenticate()
        section = factories.section(user=self.editor)

        response = self.client.post(
            action_url(section, 'archive'), {}, format='json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.data['archived_at'])

        listing = self.client.get(SECTIONS_URL)
        ids = [row['id'] for row in listing.data['results']]
        self.assertNotIn(section.id, ids)

        archived = self.client.get(
            SECTIONS_URL, {'archived': 'true'}
        )
        ids = [row['id'] for row in archived.data['results']]
        self.assertIn(section.id, ids)

    def test_archive_requires_the_archive_permission(self):
        self.authenticate(self.editor)
        section = factories.section(user=self.editor)

        response = self.client.post(
            action_url(section, 'archive'), {}, format='json'
        )

        self.assertEqual(response.status_code, 403)

    def test_archiving_twice_is_rejected(self):
        self.authenticate()
        section = factories.section(user=self.editor)
        self.client.post(
            action_url(section, 'archive'), {}, format='json'
        )

        response = self.client.post(
            action_url(section, 'archive'), {}, format='json'
        )

        self.assertEqual(response.status_code, 400)


class DeleteTests(CmsSectionLifecycleTestCase):
    def test_delete_soft_deletes_the_section(self):
        self.authenticate(self.deleter)
        section = factories.section(user=self.editor)

        response = self.client.delete(detail_url(section))

        self.assertEqual(response.status_code, 204)
        section.refresh_from_db()
        self.assertFalse(section.is_active)

    def test_delete_requires_the_delete_permission(self):
        self.authenticate(self.editor)
        section = factories.section(user=self.editor)

        response = self.client.delete(detail_url(section))

        self.assertEqual(response.status_code, 403)

    def test_delete_a_referenced_section_is_rejected(self):
        self.authenticate(self.deleter)
        section = factories.section(user=self.editor)
        factories.reference_to(section)

        response = self.client.delete(detail_url(section))

        self.assertEqual(response.status_code, 400)
        section.refresh_from_db()
        self.assertTrue(section.is_active)

    def test_references_endpoint_lists_the_reference(self):
        self.authenticate()
        section = factories.section(user=self.editor)
        factories.reference_to(section)

        response = self.client.get(
            action_url(section, 'references')
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(
            response.data[0]['model'],
            'cms_api.CmsSection',
        )
        self.assertIn('Created by', response.data[0]['fields'])


class RevisionTests(CmsSectionLifecycleTestCase):
    def test_revisions_are_listed_newest_first(self):
        self.authenticate()
        section = factories.section(user=self.editor)
        self.client.patch(
            detail_url(section),
            {'name': 'Renamed'},
            format='json',
        )

        response = self.client.get(
            action_url(section, 'revisions')
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)
        self.assertGreater(
            response.data[0]['created_at'],
            response.data[1]['created_at'],
        )

    def test_rollback_restores_old_content_and_publishes(self):
        self.authenticate()
        section = factories.section(
            user=self.editor,
            content=factories.hero_content('First'),
            live=True,
        )
        old_revision_id = section.latest_revision_id
        self.client.patch(
            detail_url(section),
            {'content': factories.hero_content('Second')},
            format='json',
        )

        response = self.client.post(
            action_url(section, 'rollback'),
            {'revision_id': old_revision_id},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data['content'][0]['value']['heading'],
            'First',
        )
        self.assertTrue(response.data['live'])
        section.refresh_from_db()
        self.assertTrue(section.live)
        self.assertGreater(section.revisions.count(), 2)

    def test_rollback_requires_the_publish_permission(self):
        self.authenticate(self.editor)
        section = factories.section(user=self.editor)

        response = self.client.post(
            action_url(section, 'rollback'),
            {'revision_id': section.latest_revision_id},
            format='json',
        )

        self.assertEqual(response.status_code, 403)

    def test_rollback_with_unknown_revision_is_rejected(self):
        self.authenticate()
        section = factories.section(user=self.editor)

        response = self.client.post(
            action_url(section, 'rollback'),
            {'revision_id': 999999},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
