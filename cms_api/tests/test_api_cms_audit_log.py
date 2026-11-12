# cms_api/tests/test_api_cms_audit_log.py
"""Audit-log event coverage and the read API (docs/cms-architecture.md
§6, §11, AD-10)."""
from datetime import timedelta

from django.utils import timezone

from rest_framework.test import APITestCase

from wagtail.log_actions import log
from wagtail.models import ModelLogEntry, PageLogEntry, Revision

from cms_api.models import CmsMediaConfig, CmsPage
from cms_api.services import (
    archive_page,
    archive_section,
    create_document,
    create_image,
    create_menu,
    create_section,
    delete_document,
    delete_image,
    delete_page,
    publish_page,
    publish_section,
    restore_page,
    rollback_page,
    rollback_section,
    run_scheduled_publishing,
    update_media_config,
)
from cms_api.services.navigation import (
    add_navigation_item,
    remove_navigation_item,
    reorder_navigation_items,
    update_navigation_item,
)
from cms_api.tests import factories


AUDIT_LOG_URL = '/api/v1/cms/audit-logs/'


class AuditEventCoverageTestCase(APITestCase):
    """Direct, service-level checks that each operation now produces
    exactly one correctly-attributed log entry."""

    def setUp(self):
        self.editor = factories.grant(
            factories.user('audit-editor'),
            CmsPage,
            'view_cmspage', 'add_cmspage', 'change_cmspage',
            'publish_cms_page', 'unpublish_cms_page',
            'archive_cms_page', 'delete_cmspage',
        )

    def test_page_archive_and_restore_are_logged(self):
        page = factories.page(self.editor, slug='p1')
        before = PageLogEntry.objects.count()

        archive_page(page=page, user=self.editor)

        self.assertEqual(PageLogEntry.objects.count(), before + 1)
        entry = PageLogEntry.objects.latest('id')
        self.assertEqual(entry.action, 'cms_api.archive')
        self.assertEqual(entry.user_id, self.editor.id)

        restore_page(page=page, user=self.editor)

        entry = PageLogEntry.objects.latest('id')
        self.assertEqual(entry.action, 'cms_api.restore')
        self.assertEqual(entry.user_id, self.editor.id)

    def test_page_delete_attributes_the_real_actor(self):
        page = factories.page(self.editor, slug='p1')

        delete_page(page=page, user=self.editor)

        entry = PageLogEntry.objects.filter(action='wagtail.delete').get()
        self.assertEqual(entry.user_id, self.editor.id)

    def test_page_rollback_uses_a_distinct_action(self):
        page = factories.page(self.editor, slug='p1', title='V1')
        publish_page(page=page, user=self.editor)
        page.refresh_from_db()
        page.title = 'V2'
        page.save()
        page.save_revision(user=self.editor, log_action='cms_api.update')
        publish_page(page=page, user=self.editor)
        first_revision = page.revisions.order_by('id').first()

        rollback_page(
            page=page, revision_id=first_revision.id, user=self.editor,
        )

        entry = PageLogEntry.objects.latest('id')
        self.assertEqual(entry.action, 'cms_api.rollback')
        self.assertNotEqual(entry.action, 'wagtail.publish')

    def test_section_rollback_uses_a_distinct_action(self):
        section = create_section(
            validated_data={
                'name': 'Hero', 'section_type': 'hero_banner',
                'content': factories.hero_content(),
            },
            user=self.editor,
        )
        publish_section(section=section, user=self.editor)
        section.name = 'Hero V2'
        section.save()
        section.save_revision(user=self.editor, log_action='wagtail.edit')
        publish_section(section=section, user=self.editor)
        first_revision = section.revisions.order_by('id').first()

        rollback_section(
            section=section, revision_id=first_revision.id,
            user=self.editor,
        )

        entry = ModelLogEntry.objects.filter(
            content_type__model='cmssection',
        ).latest('id')
        self.assertEqual(entry.action, 'cms_api.rollback')

    def test_scheduled_sweep_logs_with_a_null_system_actor(self):
        page = factories.page(self.editor, slug='scheduled')
        publish_page(
            page=page, user=self.editor,
            go_live_at=timezone.now() + timedelta(days=1),
        )
        page.refresh_from_db()
        past = timezone.now() - timedelta(minutes=1)
        revision = Revision.objects.get(pk=page.latest_revision_id)
        revision.content['go_live_at'] = past.isoformat()
        revision.approved_go_live_at = past
        revision.save(update_fields=['content', 'approved_go_live_at'])

        run_scheduled_publishing()

        entry = PageLogEntry.objects.filter(
            action='wagtail.publish.scheduled',
        ).get()
        self.assertIsNone(entry.user_id)


class NavigationAuditTestCase(APITestCase):
    def setUp(self):
        self.user = factories.user('audit-nav')

    def test_menu_crud_is_logged(self):
        menu = create_menu(
            validated_data={'name': 'Header', 'key': 'HEADER'},
            user=self.user,
        )
        self.assertTrue(
            ModelLogEntry.objects.filter(
                content_type__model='cmsnavigationmenu',
                action='wagtail.create',
                object_id=str(menu.pk),
                user_id=self.user.id,
            ).exists()
        )

        from cms_api.services import update_menu
        update_menu(
            menu=menu, validated_data={'name': 'New'}, user=self.user,
        )
        self.assertTrue(
            ModelLogEntry.objects.filter(
                content_type__model='cmsnavigationmenu',
                action='wagtail.edit',
                object_id=str(menu.pk),
            ).exists()
        )

        from cms_api.services import delete_menu as _delete_menu
        _delete_menu(menu=menu, user=self.user)
        self.assertTrue(
            ModelLogEntry.objects.filter(
                content_type__model='cmsnavigationmenu',
                action='wagtail.delete',
                object_id=str(menu.pk),
            ).exists()
        )

    def test_item_create_update_delete_are_logged(self):
        menu = create_menu(
            validated_data={'name': 'Header', 'key': 'HEADER'},
            user=self.user,
        )
        item = add_navigation_item(
            menu=menu,
            validated_data={
                'label': 'Docs', 'link_type': 'EXTERNAL',
                'external_url': 'https://example.com',
            },
            user=self.user,
        )
        self.assertTrue(
            ModelLogEntry.objects.filter(
                content_type__model='cmsnavigationitem',
                action='wagtail.create',
                object_id=str(item.pk),
            ).exists()
        )

        update_navigation_item(
            menu=menu, item=item,
            validated_data={'label': 'Docs V2'}, user=self.user,
        )
        self.assertTrue(
            ModelLogEntry.objects.filter(
                content_type__model='cmsnavigationitem',
                action='wagtail.edit',
                object_id=str(item.pk),
            ).exists()
        )

        item_pk = item.pk
        remove_navigation_item(menu=menu, item=item, user=self.user)
        self.assertTrue(
            ModelLogEntry.objects.filter(
                content_type__model='cmsnavigationitem',
                action='wagtail.delete',
                object_id=str(item_pk),
            ).exists()
        )

    def test_reorder_creates_exactly_one_entry_against_the_menu(self):
        menu = create_menu(
            validated_data={'name': 'Header', 'key': 'HEADER'},
            user=self.user,
        )
        first = add_navigation_item(
            menu=menu,
            validated_data={
                'label': 'A', 'link_type': 'EXTERNAL',
                'external_url': 'https://a.example.com',
            },
            user=self.user,
        )
        second = add_navigation_item(
            menu=menu,
            validated_data={
                'label': 'B', 'link_type': 'EXTERNAL',
                'external_url': 'https://b.example.com',
            },
            user=self.user,
        )
        before = ModelLogEntry.objects.filter(
            action='cms_api.navigation.reorder',
        ).count()

        reorder_navigation_items(
            menu=menu, parent_id=None,
            order=[second.pk, first.pk], user=self.user,
        )

        reorder_entries = ModelLogEntry.objects.filter(
            action='cms_api.navigation.reorder',
        )
        self.assertEqual(reorder_entries.count(), before + 1)
        entry = reorder_entries.latest('id')
        self.assertEqual(entry.content_type.model, 'cmsnavigationmenu')
        self.assertEqual(entry.object_id, str(menu.pk))


class MediaAuditTestCase(APITestCase):
    def setUp(self):
        self.user = factories.user('audit-media')

    def test_image_create_update_delete_are_logged(self):
        image = create_image(
            validated_data={
                'title': 'Pic', 'file': factories.image_upload(),
            },
            user=self.user,
        )
        self.assertTrue(
            ModelLogEntry.objects.filter(
                content_type__model='image',
                action='wagtail.create',
                object_id=str(image.pk),
                user_id=self.user.id,
            ).exists()
        )

        from cms_api.services import update_image
        update_image(
            image=image, validated_data={'title': 'Pic2'},
            user=self.user,
        )
        self.assertTrue(
            ModelLogEntry.objects.filter(
                content_type__model='image',
                action='wagtail.edit',
                object_id=str(image.pk),
            ).exists()
        )

        image_pk = image.pk
        delete_image(image=image, user=self.user)
        self.assertTrue(
            ModelLogEntry.objects.filter(
                content_type__model='image',
                action='wagtail.delete',
                object_id=str(image_pk),
            ).exists()
        )

    def test_document_create_and_delete_are_logged(self):
        document = create_document(
            validated_data={
                'title': 'Doc', 'file': factories.document_upload(),
            },
            user=self.user,
        )
        self.assertTrue(
            ModelLogEntry.objects.filter(
                content_type__model='document',
                action='wagtail.create',
                object_id=str(document.pk),
            ).exists()
        )

        document_pk = document.pk
        delete_document(document=document, user=self.user)
        self.assertTrue(
            ModelLogEntry.objects.filter(
                content_type__model='document',
                action='wagtail.delete',
                object_id=str(document_pk),
            ).exists()
        )

    def test_media_config_update_is_logged(self):
        config = CmsMediaConfig.get_solo()

        update_media_config(
            config=config,
            validated_data={'max_image_upload_size': 1234},
            user=self.user,
        )

        self.assertTrue(
            ModelLogEntry.objects.filter(
                content_type__model='cmsmediaconfig',
                action='wagtail.edit',
                user_id=self.user.id,
            ).exists()
        )


class AuditLogApiTestCase(APITestCase):
    def setUp(self):
        self.viewer = factories.grant(
            factories.user('audit-viewer'),
            CmsPage,
            'view_cmspage',
        )
        self.editor = factories.grant(
            factories.user('audit-api-editor'),
            CmsPage,
            'view_cmspage', 'add_cmspage', 'change_cmspage',
            'publish_cms_page',
        )

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.viewer)


class PermissionTests(AuditLogApiTestCase):
    def test_requires_authentication(self):
        response = self.client.get(AUDIT_LOG_URL)

        self.assertEqual(response.status_code, 401)

    def test_requires_view_cmspage(self):
        self.client.force_authenticate(user=factories.user('no-perm'))

        response = self.client.get(AUDIT_LOG_URL)

        self.assertEqual(response.status_code, 403)

    def test_view_cmspage_holder_can_read(self):
        self.authenticate()

        response = self.client.get(AUDIT_LOG_URL)

        self.assertEqual(response.status_code, 200)


class EmptyAndCombinedResultsTests(AuditLogApiTestCase):
    def test_empty_results(self):
        self.authenticate()

        response = self.client.get(AUDIT_LOG_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 0)
        self.assertEqual(response.data['results'], [])

    def test_combines_page_and_model_sources_in_order(self):
        page = factories.page(self.editor, slug='p1')
        publish_page(page=page, user=self.editor)
        section = factories.section(user=self.editor)
        archive_section(section=section, user=self.editor)
        create_menu(
            validated_data={'name': 'Header', 'key': 'HEADER'},
            user=self.editor,
        )
        self.authenticate()

        response = self.client.get(AUDIT_LOG_URL)

        self.assertEqual(response.status_code, 200)
        models_seen = {row['model'] for row in response.data['results']}
        self.assertIn('cms_api.CmsPage', models_seen)
        self.assertIn('cms_api.CmsSection', models_seen)
        self.assertIn('cms_api.CmsNavigationMenu', models_seen)
        timestamps = [row['timestamp'] for row in response.data['results']]
        self.assertEqual(timestamps, sorted(timestamps, reverse=True))

    def test_system_actor_is_rendered_as_null(self):
        page = factories.page(self.editor, slug='scheduled')
        publish_page(
            page=page, user=self.editor,
            go_live_at=timezone.now() + timedelta(days=1),
        )
        page.refresh_from_db()
        past = timezone.now() - timedelta(minutes=1)
        revision = Revision.objects.get(pk=page.latest_revision_id)
        revision.content['go_live_at'] = past.isoformat()
        revision.approved_go_live_at = past
        revision.save(update_fields=['content', 'approved_go_live_at'])
        run_scheduled_publishing()
        self.authenticate()

        response = self.client.get(AUDIT_LOG_URL)

        scheduled_rows = [
            row for row in response.data['results']
            if row['action'] == 'wagtail.publish.scheduled'
        ]
        self.assertEqual(len(scheduled_rows), 1)
        self.assertIsNone(scheduled_rows[0]['actor'])
        self.assertIsNone(scheduled_rows[0]['actor_id'])


class AllowlistTests(AuditLogApiTestCase):
    def test_unrelated_activity_is_excluded(self):
        page = factories.page(self.editor, slug='p1')
        publish_page(page=page, user=self.editor)
        # Simulate unrelated activity on a non-CMS model: this proves
        # the content-type allowlist, not just that nothing else
        # happens to log today.
        log(self.viewer, 'wagtail.edit', user=self.editor)
        self.authenticate()

        response = self.client.get(AUDIT_LOG_URL)

        models_seen = {row['model'] for row in response.data['results']}
        self.assertIn('cms_api.CmsPage', models_seen)
        self.assertNotIn('user_api.User', models_seen)

    def test_content_type_filter_restricts_to_one_source(self):
        page = factories.page(self.editor, slug='p1')
        publish_page(page=page, user=self.editor)
        create_menu(
            validated_data={'name': 'Header', 'key': 'HEADER'},
            user=self.editor,
        )
        self.authenticate()

        response = self.client.get(
            AUDIT_LOG_URL, {'content_type': 'cmspage'},
        )

        self.assertEqual(response.status_code, 200)
        models_seen = {row['model'] for row in response.data['results']}
        self.assertEqual(models_seen, {'cms_api.CmsPage'})

    def test_invalid_content_type_is_rejected(self):
        self.authenticate()

        response = self.client.get(
            AUDIT_LOG_URL, {'content_type': 'product'},
        )

        self.assertEqual(response.status_code, 400)

    def test_action_filter(self):
        page = factories.page(self.editor, slug='p1')
        publish_page(page=page, user=self.editor)
        archive_page(page=page, user=self.editor)
        self.authenticate()

        response = self.client.get(
            AUDIT_LOG_URL, {'action': 'cms_api.archive'},
        )

        actions_seen = {row['action'] for row in response.data['results']}
        self.assertEqual(actions_seen, {'cms_api.archive'})


class DateFilteringAndPaginationTests(AuditLogApiTestCase):
    def test_excludes_entries_outside_the_requested_range(self):
        page = factories.page(self.editor, slug='p1')
        publish_page(page=page, user=self.editor)
        entry = PageLogEntry.objects.latest('id')
        far_past = timezone.now() - timedelta(days=200)
        PageLogEntry.objects.filter(pk=entry.pk).update(
            timestamp=far_past,
        )
        self.authenticate()

        response = self.client.get(
            AUDIT_LOG_URL,
            {
                'start_date': timezone.now().date().isoformat(),
                'end_date': timezone.now().date().isoformat(),
            },
        )

        self.assertEqual(response.data['results'], [])

    def test_includes_entries_inside_the_requested_range(self):
        page = factories.page(self.editor, slug='p1')
        publish_page(page=page, user=self.editor)
        self.authenticate()

        response = self.client.get(
            AUDIT_LOG_URL,
            {
                'start_date': (
                    timezone.now() - timedelta(days=1)
                ).isoformat(),
                'end_date': (
                    timezone.now() + timedelta(days=1)
                ).isoformat(),
            },
        )

        self.assertGreater(len(response.data['results']), 0)

    def test_start_after_end_is_rejected(self):
        self.authenticate()

        response = self.client.get(
            AUDIT_LOG_URL,
            {
                'start_date': timezone.now().isoformat(),
                'end_date': (
                    timezone.now() - timedelta(days=1)
                ).isoformat(),
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_default_window_is_ninety_days(self):
        from cms_api.services import resolve_audit_log_window

        start, end = resolve_audit_log_window()

        self.assertAlmostEqual(
            (end - start).days, 90, delta=1,
        )

    def test_requested_range_is_capped_at_365_days(self):
        from cms_api.services import resolve_audit_log_window

        end = timezone.now()
        start = end - timedelta(days=1000)

        clamped_start, clamped_end = resolve_audit_log_window(
            start, end,
        )

        self.assertLessEqual(
            (clamped_end - clamped_start).days, 365,
        )

    def test_pagination_shape(self):
        for i in range(12):
            page = factories.page(self.editor, slug=f'p{i}')
            publish_page(page=page, user=self.editor)
        self.authenticate()

        response = self.client.get(AUDIT_LOG_URL)

        self.assertEqual(response.status_code, 200)
        self.assertIn('count', response.data)
        self.assertIn('total_pages', response.data)
        self.assertIn('next', response.data)
        self.assertIn('results', response.data)
        self.assertLessEqual(len(response.data['results']), 10)
