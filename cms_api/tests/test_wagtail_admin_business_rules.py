# cms_api/tests/test_wagtail_admin_business_rules.py
"""Wagtail Admin enforcement of the same business rules the DRF
CMS API enforces (docs/cms-architecture.md Phase 5B):

- reserved paths (``CMS_RESERVED_PATHS``) cannot be published via
  the admin, neither through the page form nor a publish that skips
  the form;
- a page (or subtree) referenced by navigation items cannot be
  deleted from the admin — never a raw ``ProtectedError``;
- slug-change redirects created on admin publishes match the DRF
  service output exactly once (no signal/explicit duplication);
- section delete through the admin goes through ``delete_section``:
  dependency guard, soft delete, acting-user log entry.

Uses Django's session-based test client, like
``test_wagtail_admin_rbac.py`` — the admin is a session-auth surface.
"""
from django.test import TestCase, override_settings
from django.urls import reverse

from rest_framework.exceptions import ValidationError

from wagtail.contrib.redirects.models import Redirect
from wagtail.models import ModelLogEntry, PageLogEntry

from cms_api.models import CmsPage, CmsSection
from cms_api.services import delete_page, publish_page, update_page
from cms_api.tests import factories


def admin_url(name, *args):
    return reverse(name, args=args)


class AdminPageTestCase(TestCase):
    """Shared setup: a logged-in CMS editor."""

    def setUp(self):
        self.user = factories.grant(
            factories.user('br-admin', is_staff=True),
            CmsPage,
            'view_cmspage', 'add_cmspage', 'change_cmspage',
            'publish_cms_page', 'delete_cmspage',
        )
        self.client.force_login(self.user)

    def publish_via_admin(self, page, **overrides):
        # Wagtail's edit view treats the "action-publish" key as the
        # publish trigger (WagtailEditView.action_name_and_method);
        # anything else falls back to "save" (draft only).
        form = {
            'title': page.title,
            'slug': page.slug,
            'template_key': 'blank',
            'action-publish': 'Publish',
        }
        form.update(overrides)
        return self.client.post(
            admin_url('wagtailadmin_pages:edit', page.pk), form,
        )


@override_settings(CMS_RESERVED_PATHS=['/checkout/'])
class ReservedPathAdminTestCase(AdminPageTestCase):
    def test_form_blocks_slug_change_to_reserved_path(self):
        page = factories.page(self.user, slug='home2')

        response = self.publish_via_admin(page, slug='checkout')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'reserved')
        page.refresh_from_db()
        self.assertEqual(page.slug, 'home2')
        self.assertFalse(page.live)

    def test_publish_vetoed_when_path_already_reserved(self):
        """The form check skips an unchanged slug; the
        before_publish_page hook must still veto the publish."""
        page = factories.page(self.user, slug='checkout')

        response = self.publish_via_admin(page)

        self.assertEqual(response.status_code, 302)
        page.refresh_from_db()
        self.assertFalse(page.live)

    def test_non_reserved_path_publishes_normally(self):
        page = factories.page(self.user, slug='normal')

        response = self.publish_via_admin(page)

        self.assertEqual(response.status_code, 302)
        page.refresh_from_db()
        self.assertTrue(page.live)
        self.assertTrue(
            PageLogEntry.objects.filter(
                action='wagtail.publish', page=page,
            ).exists()
        )


class AdminSlugRedirectTestCase(AdminPageTestCase):
    def test_slug_change_publish_creates_exactly_one_redirect(self):
        page = factories.page(self.user, slug='old')
        self.publish_via_admin(page)

        self.publish_via_admin(page, slug='new')

        redirect = Redirect.objects.get(
            old_path=Redirect.normalise_path('/old/'),
        )
        self.assertEqual(redirect.redirect_page_id, page.pk)
        self.assertEqual(Redirect.objects.count(), 1)
        self.assertEqual(
            PageLogEntry.objects.filter(
                action='cms_api.redirect.create',
            ).count(),
            1,
        )

    def test_rename_back_drops_stale_redirect(self):
        page = factories.page(self.user, slug='old')
        self.publish_via_admin(page)
        self.publish_via_admin(page, slug='new')

        self.publish_via_admin(page, slug='old')

        self.assertFalse(
            Redirect.objects.filter(
                old_path=Redirect.normalise_path('/old/'),
            ).exists(),
        )
        self.assertTrue(
            Redirect.objects.filter(
                old_path=Redirect.normalise_path('/new/'),
            ).exists(),
        )

    def test_drf_publish_creates_one_redirect_no_signal_duplicate(
        self,
    ):
        user = self.user
        page = factories.page(user, slug='old')
        publish_page(page=page, user=user)
        update_page(
            page=page, validated_data={'slug': 'new'}, user=user,
        )

        publish_page(page=page, user=user)

        self.assertEqual(
            Redirect.objects.filter(
                old_path=Redirect.normalise_path('/old/'),
            ).count(),
            1,
        )
        self.assertEqual(
            PageLogEntry.objects.filter(
                action='cms_api.redirect.create',
            ).count(),
            1,
        )


class NavReferencedDeleteTestCase(AdminPageTestCase):
    def test_nav_referenced_page_cannot_be_deleted_via_admin(self):
        page = factories.page(self.user, slug='nav1')
        menu = factories.navigation_menu(user=self.user)
        item = factories.navigation_item(menu, page=page)

        response = self.client.get(
            admin_url('wagtailadmin_pages:delete', page.pk),
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(CmsPage.objects.filter(pk=page.pk).exists())
        self.assertTrue(
            item.__class__.objects.filter(pk=item.pk).exists(),
        )

    def test_descendant_nav_reference_blocks_parent_delete_admin(
        self,
    ):
        parent = factories.page(self.user, slug='parent')
        child = factories.page(self.user, slug='child', parent=parent)
        menu = factories.navigation_menu(user=self.user)
        factories.navigation_item(menu, page=child)

        response = self.client.post(
            admin_url('wagtailadmin_pages:delete', parent.pk),
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            CmsPage.objects.filter(pk=parent.pk).exists(),
        )
        self.assertTrue(CmsPage.objects.filter(pk=child.pk).exists())

    def test_descendant_nav_reference_blocks_drf_delete(self):
        """The DRF guard returns the structured dependency response,
        never a raw ProtectedError from the PROTECT foreign key."""
        parent = factories.page(self.user, slug='parent2')
        child = factories.page(self.user, slug='child2', parent=parent)
        menu = factories.navigation_menu(user=self.user)
        factories.navigation_item(menu, page=child)

        with self.assertRaises(ValidationError) as raised:
            delete_page(
                page=parent, user=self.user, acknowledge=True,
            )

        self.assertIn('dependencies', raised.exception.detail)
        self.assertTrue(
            CmsPage.objects.filter(pk=parent.pk).exists(),
        )


class SectionAdminDeleteTestCase(TestCase):
    def setUp(self):
        self.user = factories.grant(
            factories.user('br-section', is_staff=True),
            CmsSection,
            'view_cmssection', 'change_cmssection',
            'delete_cmssection',
        )
        self.client.force_login(self.user)

    def test_admin_section_delete_soft_deletes_with_user_log(self):
        section = factories.section(user=self.user)

        response = self.client.post(
            admin_url(
                'wagtailsnippets_cms_api_cmssection:delete',
                section.pk,
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            CmsSection.objects.filter(pk=section.pk).exists(),
        )
        section.refresh_from_db()
        self.assertFalse(section.is_active)
        log_entry = ModelLogEntry.objects.filter(
            action='wagtail.delete',
            object_id=str(section.pk),
        ).first()
        self.assertIsNotNone(log_entry)
        self.assertEqual(log_entry.user_id, self.user.pk)

    def test_referenced_section_delete_refused_via_admin(self):
        target = factories.section(name='Referenced target')
        factories.reference_to(target)

        response = self.client.post(
            admin_url(
                'wagtailsnippets_cms_api_cmssection:delete',
                target.pk,
            ),
        )

        self.assertIn(response.status_code, (302, 403))
        self.assertTrue(
            CmsSection.objects.filter(pk=target.pk).exists(),
        )
        target.refresh_from_db()
        self.assertTrue(target.is_active)
