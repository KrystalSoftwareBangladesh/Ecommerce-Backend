# cms_api/tests/test_wagtail_admin_rbac.py
"""Wagtail Admin authorization, backed by the existing CMS RBAC
(docs/cms-architecture.md AD-11, Phase 5A).

Uses Django's session-based test client (``force_login``), not DRF's
``force_authenticate``: Wagtail Admin is a conventional Django admin
surface (session auth + middleware), unlike the DRF CMS API.
"""
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from wagtail.models import GroupPagePermission, Page

from cms_api.models import CmsPage, CmsSection
from cms_api.tests import factories
from cms_api.wagtail_permissions import (
    CmsSectionPermissionPolicy,
    CmsSectionUnpublishView,
    PAGE_ACTION_CODENAMES,
    SECTION_ACTION_CODENAMES,
)


def admin_url(name, *args):
    return reverse(name, args=args)


class WagtailAdminAccessTestCase(TestCase):
    """The wagtailadmin.access_admin gate (is_staff/superuser only)."""

    def test_non_staff_user_cannot_access_admin(self):
        user = factories.user('rbac-nonstaff', is_staff=False)
        self.client.force_login(user)

        response = self.client.get(admin_url('wagtailadmin_home'))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith('/cms-admin/login/'))

    def test_staff_user_without_any_cms_permission_can_reach_dashboard(
        self,
    ):
        """is_staff alone grants entry; per-action authorization is
        enforced separately, by the policies, not the entry gate."""
        user = factories.user('rbac-staff-noperm', is_staff=True)
        self.client.force_login(user)

        response = self.client.get(admin_url('wagtailadmin_home'))

        self.assertEqual(response.status_code, 200)

    def test_staff_user_with_cms_permissions_can_reach_dashboard(self):
        user = factories.grant(
            factories.user('rbac-staff-full', is_staff=True),
            CmsPage,
            'view_cmspage', 'add_cmspage', 'change_cmspage',
            'publish_cms_page',
        )
        self.client.force_login(user)

        response = self.client.get(admin_url('wagtailadmin_home'))

        self.assertEqual(response.status_code, 200)

    def test_superuser_without_is_staff_still_gets_in(self):
        """Preserve superuser access regardless of is_staff."""
        user = factories.user('rbac-super-nostaff')
        user.is_superuser = True
        user.is_staff = False
        user.save()
        self.client.force_login(user)

        response = self.client.get(admin_url('wagtailadmin_home'))

        self.assertEqual(response.status_code, 200)

    def test_no_group_page_permission_or_duplicate_codenames_created(self):
        before_gpp = GroupPagePermission.objects.count()
        before_dupe = Permission.objects.filter(
            codename__in=[
                'publish_cmspage', 'unpublish_cmspage',
                'unpublish_cmssection',
            ],
        ).count()

        factories.grant(
            factories.user('rbac-no-side-effects', is_staff=True),
            CmsPage,
            'view_cmspage', 'add_cmspage', 'change_cmspage',
            'publish_cms_page', 'delete_cmspage', 'unpublish_cms_page',
            'archive_cms_page',
        )
        self.client.force_login(
            factories.user('rbac-no-side-effects-2', is_staff=True),
        )
        self.client.get(admin_url('wagtailadmin_home'))
        self.client.get(admin_url('wagtailadmin_explore_root'))

        self.assertEqual(
            GroupPagePermission.objects.count(), before_gpp,
        )
        self.assertEqual(
            Permission.objects.filter(
                codename__in=[
                    'publish_cmspage', 'unpublish_cmspage',
                    'unpublish_cmssection',
                ],
            ).count(),
            before_dupe,
        )


class PageAdminActionsTestCase(TestCase):
    def setUp(self):
        self.root = Page.objects.get(depth=1)

    def grant(self, username, *codenames):
        return factories.grant(
            factories.user(username, is_staff=True), CmsPage, *codenames,
        )

    def test_view_permission_grants_read_level_instance_access(self):
        """The explorer *view* itself is gated by Wagtail's own
        IndexView.any_permission_required, which never includes
        "view" (wagtail/admin/views/pages/listing.py) — a design
        choice native to Wagtail's page admin, not something this
        integration changes. What this integration does control is
        which pages a "view" check resolves true for, confirmed
        directly at the policy level."""
        user = self.grant('page-view-only', 'view_cmspage')
        page = factories.page(user, slug='p1')
        from wagtail.permissions import page_permission_policy

        self.assertIn(
            page.pk,
            page_permission_policy.instances_user_has_any_permission_for(
                user, {'view'},
            ).values_list('pk', flat=True),
        )

    def test_view_only_user_cannot_access_the_explorer(self):
        """Documents the Wagtail-native limitation above at the HTTP
        level: view_cmspage alone does not admit a user to the page
        explorer, because Wagtail's own IndexView requires add,
        change, publish, bulk_delete, lock or unlock — never view."""
        user = self.grant('page-view-only-explorer', 'view_cmspage')
        factories.page(user, slug='p1b')
        self.client.force_login(user)

        response = self.client.get(
            admin_url('wagtailadmin_explore', self.root.pk),
        )

        self.assertEqual(response.status_code, 302)

    def test_view_only_user_cannot_edit(self):
        user = self.grant('page-view-only-2', 'view_cmspage')
        page = factories.page(user, slug='p2')
        self.client.force_login(user)

        response = self.client.get(
            admin_url('wagtailadmin_pages:edit', page.pk),
        )

        self.assertEqual(response.status_code, 302)

    def test_change_permission_allows_edit(self):
        user = self.grant(
            'page-editor', 'view_cmspage', 'change_cmspage',
        )
        page = factories.page(user, slug='p3')
        self.client.force_login(user)

        response = self.client.get(
            admin_url('wagtailadmin_pages:edit', page.pk),
        )

        self.assertEqual(response.status_code, 200)

    def test_change_only_user_cannot_delete(self):
        """View permission (and change permission) must not grant
        delete — Wagtail's own can_delete() succeeds on 'change'
        alone; this project requires delete_cmspage specifically."""
        user = self.grant(
            'page-change-only', 'view_cmspage', 'change_cmspage',
        )
        page = factories.page(user, slug='p4')
        self.client.force_login(user)

        response = self.client.get(
            admin_url('wagtailadmin_pages:delete', page.pk),
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(CmsPage.objects.filter(pk=page.pk).exists())

    def test_delete_permission_allows_delete(self):
        user = self.grant(
            'page-deleter', 'view_cmspage', 'delete_cmspage',
        )
        page = factories.page(user, slug='p5')
        self.client.force_login(user)

        response = self.client.get(
            admin_url('wagtailadmin_pages:delete', page.pk),
        )

        self.assertEqual(response.status_code, 200)

    def test_publish_only_user_cannot_unpublish(self):
        """publish_cms_page must not imply unpublish_cms_page."""
        user = self.grant(
            'page-publish-only', 'view_cmspage', 'change_cmspage',
            'publish_cms_page',
        )
        page = factories.page(user, slug='p6')
        from cms_api.services import publish_page
        publish_page(page=page, user=user)
        self.client.force_login(user)

        response = self.client.get(
            admin_url('wagtailadmin_pages:unpublish', page.pk),
        )

        self.assertEqual(response.status_code, 302)
        page.refresh_from_db()
        self.assertTrue(page.live)

    def test_unpublish_permission_allows_unpublish(self):
        user = self.grant(
            'page-unpublisher', 'view_cmspage', 'change_cmspage',
            'publish_cms_page', 'unpublish_cms_page',
        )
        page = factories.page(user, slug='p7')
        from cms_api.services import publish_page
        publish_page(page=page, user=user)
        self.client.force_login(user)

        response = self.client.post(
            admin_url('wagtailadmin_pages:unpublish', page.pk),
            {'next': admin_url('wagtailadmin_explore', self.root.pk)},
        )

        self.assertEqual(response.status_code, 302)
        page.refresh_from_db()
        self.assertFalse(page.live)

    def test_can_publish_uses_the_exact_custom_codename(self):
        """Direct, precise check of the mapping the task requires:
        'existing custom publish permissions work correctly'."""
        page = factories.page(
            self.grant('page-publish-check', 'view_cmspage'), slug='p8',
        )
        holder = self.grant(
            'page-publish-holder', 'view_cmspage', 'publish_cms_page',
        )
        non_holder = self.grant(
            'page-publish-nonholder', 'view_cmspage', 'change_cmspage',
        )

        self.assertTrue(
            page.permissions_for_user(holder).can_publish()
        )
        self.assertFalse(
            page.permissions_for_user(non_holder).can_publish()
        )

    def test_missing_permission_denies_add_subpage(self):
        user = self.grant('page-no-add', 'view_cmspage')
        self.client.force_login(user)

        response = self.client.get(
            admin_url(
                'wagtailadmin_pages:add',
                'cms_api', 'cmspage', self.root.pk,
            ),
        )

        self.assertEqual(response.status_code, 302)

    def test_add_permission_allows_top_level_page_creation_form(self):
        """Exercises the root-page fallback in
        CmsPagePermissionPolicy.get_all_permissions_for_user: the root
        is a plain wagtailcore.Page, not a CmsPage, so it uses
        Wagtail's own default PagePermissionTester, fed from that
        fallback."""
        user = self.grant('page-add-root', 'view_cmspage', 'add_cmspage')
        self.client.force_login(user)

        response = self.client.get(
            admin_url(
                'wagtailadmin_pages:add',
                'cms_api', 'cmspage', self.root.pk,
            ),
        )

        self.assertEqual(response.status_code, 200)

    def test_superuser_has_every_page_action(self):
        user = factories.superuser('page-super')
        page = factories.page(user, slug='p9')
        tester = page.permissions_for_user(user)

        self.assertTrue(tester.can_edit())
        self.assertTrue(tester.can_delete())
        self.assertTrue(tester.can_publish())


class SectionAdminActionsTestCase(TestCase):
    def grant(self, username, *codenames):
        return factories.grant(
            factories.user(username, is_staff=True), CmsSection, *codenames,
        )

    def test_section_list_requires_staff_and_a_cms_permission(self):
        user = self.grant('section-viewer', 'view_cmssection')
        factories.section(user=user)
        self.client.force_login(user)

        response = self.client.get(
            admin_url(
                'wagtailsnippets_cms_api_cmssection:list',
            ),
        )

        self.assertEqual(response.status_code, 200)

    def test_view_only_user_cannot_edit_section(self):
        owner = self.grant('section-owner', 'view_cmssection')
        section = factories.section(user=owner)
        viewer = self.grant('section-view-only', 'view_cmssection')
        self.client.force_login(viewer)

        response = self.client.get(
            admin_url(
                'wagtailsnippets_cms_api_cmssection:edit', section.pk,
            ),
        )

        self.assertEqual(response.status_code, 302)

    def test_change_permission_allows_section_edit(self):
        user = self.grant(
            'section-editor', 'view_cmssection', 'change_cmssection',
        )
        section = factories.section(user=user)
        self.client.force_login(user)

        response = self.client.get(
            admin_url(
                'wagtailsnippets_cms_api_cmssection:edit', section.pk,
            ),
        )

        self.assertEqual(response.status_code, 200)

    def test_change_only_user_cannot_delete_section(self):
        user = self.grant(
            'section-change-only', 'view_cmssection', 'change_cmssection',
        )
        section = factories.section(user=user)
        self.client.force_login(user)

        response = self.client.get(
            admin_url(
                'wagtailsnippets_cms_api_cmssection:delete', section.pk,
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(CmsSection.objects.filter(pk=section.pk).exists())

    def test_delete_permission_allows_section_delete(self):
        user = self.grant(
            'section-deleter', 'view_cmssection', 'delete_cmssection',
        )
        section = factories.section(user=user)
        self.client.force_login(user)

        response = self.client.get(
            admin_url(
                'wagtailsnippets_cms_api_cmssection:delete', section.pk,
            ),
        )

        self.assertEqual(response.status_code, 200)

    def test_publish_only_user_cannot_unpublish_section(self):
        """The exact divergence the audit found: Wagtail's own
        UnpublishView.permission_required == "publish", which would
        let a publish-only holder unpublish too unless overridden."""
        user = self.grant(
            'section-publish-only', 'view_cmssection',
            'change_cmssection', 'publish_cms_section',
        )
        section = factories.section(user=user)
        from cms_api.services import publish_section
        publish_section(section=section, user=user)
        self.client.force_login(user)

        response = self.client.get(
            admin_url(
                'wagtailsnippets_cms_api_cmssection:unpublish',
                section.pk,
            ),
        )

        self.assertEqual(response.status_code, 302)
        section.refresh_from_db()
        self.assertTrue(section.live)

    def test_unpublish_permission_allows_section_unpublish(self):
        user = self.grant(
            'section-unpublisher', 'view_cmssection',
            'change_cmssection', 'publish_cms_section',
            'unpublish_cms_section',
        )
        section = factories.section(user=user)
        from cms_api.services import publish_section
        publish_section(section=section, user=user)
        self.client.force_login(user)

        response = self.client.post(
            admin_url(
                'wagtailsnippets_cms_api_cmssection:unpublish',
                section.pk,
            ),
        )

        self.assertEqual(response.status_code, 302)
        section.refresh_from_db()
        self.assertFalse(section.live)

    def test_can_publish_uses_the_exact_custom_codename(self):
        policy = CmsSectionPermissionPolicy(CmsSection)
        holder = self.grant(
            'section-publish-holder', 'view_cmssection',
            'publish_cms_section',
        )
        non_holder = self.grant(
            'section-publish-nonholder', 'view_cmssection',
            'change_cmssection',
        )

        self.assertTrue(policy.user_has_permission(holder, 'publish'))
        self.assertFalse(
            policy.user_has_permission(non_holder, 'publish')
        )

    def test_superuser_has_every_section_action(self):
        policy = CmsSectionPermissionPolicy(CmsSection)
        user = factories.superuser('section-super')

        self.assertTrue(policy.user_has_permission(user, 'publish'))
        self.assertTrue(policy.user_has_permission(user, 'unpublish'))
        self.assertTrue(policy.user_has_permission(user, 'change'))
        self.assertTrue(policy.user_has_permission(user, 'delete'))

    def test_non_staff_user_denied_despite_holding_permission(self):
        user = factories.grant(
            factories.user('section-nonstaff', is_staff=False),
            CmsSection,
            'view_cmssection', 'publish_cms_section',
        )
        policy = CmsSectionPermissionPolicy(CmsSection)

        self.assertFalse(policy.user_has_permission(user, 'publish'))


class PermissionMappingUnitTestCase(TestCase):
    """Direct assertions on the mapping tables themselves, so a
    future edit that silently changes a mapping is caught here even
    if no admin view happens to exercise that exact action."""

    def test_page_action_codenames(self):
        self.assertEqual(
            PAGE_ACTION_CODENAMES['publish'], 'publish_cms_page',
        )
        self.assertEqual(
            PAGE_ACTION_CODENAMES['unpublish'], 'unpublish_cms_page',
        )
        self.assertEqual(
            PAGE_ACTION_CODENAMES['delete'], 'delete_cmspage',
        )
        self.assertEqual(
            PAGE_ACTION_CODENAMES['view'], 'view_cmspage',
        )

    def test_section_action_codenames(self):
        self.assertEqual(
            SECTION_ACTION_CODENAMES['publish'], 'publish_cms_section',
        )
        self.assertEqual(
            SECTION_ACTION_CODENAMES['unpublish'],
            'unpublish_cms_section',
        )

    def test_unpublish_view_checks_unpublish_codename_only(self):
        self.assertTrue(
            hasattr(CmsSectionUnpublishView, 'user_has_permission')
        )
