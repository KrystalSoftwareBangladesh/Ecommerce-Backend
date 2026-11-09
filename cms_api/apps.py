# cms_api/apps.py
from django.apps import AppConfig


class CmsApiConfig(AppConfig):
    default_auto_field = (
        "django.db.models.BigAutoField"
    )
    name = "cms_api"
    verbose_name = "CMS"

    def ready(self):
        # Import wagtail_hooks modules (registering the CMS snippets)
        # eagerly: SnippetChooserBlock content validation resolves
        # chooser widgets, which needs the snippet registrations to
        # have happened even in API-only processes where Wagtail's
        # hook discovery would never run.
        from wagtail.hooks import search_for_hooks

        search_for_hooks()

        self._install_wagtail_admin_rbac()

    def _install_wagtail_admin_rbac(self):
        """Point Wagtail Admin's page permissions at the existing CMS
        RBAC (docs/cms-architecture.md AD-11, Phase 5A).

        ``wagtail.permissions.page_permission_policy`` is a single
        module-level instance that every Wagtail Admin view reads,
        whether imported as a local name or stored as a class
        attribute (``wagtail.admin.views.pages.listing.IndexView.
        permission_policy = page_permission_policy``, bound when that
        module is first imported). Rebinding the module attribute to
        a *new* object would miss every reference already bound
        elsewhere; reassigning ``__class__`` on the existing instance
        changes what every one of those references sees, since they
        all point at the same object. This runs once, in ``ready()``,
        before any admin view module can have been imported.
        """
        from wagtail.permissions import page_permission_policy

        from cms_api.models import CmsPage
        from cms_api.wagtail_permissions import (
            CmsPagePermissionPolicy,
            CmsPagePermissionTester,
        )

        page_permission_policy.__class__ = CmsPagePermissionPolicy

        def permissions_for_user(self, user):
            return CmsPagePermissionTester(user, self)

        CmsPage.permissions_for_user = permissions_for_user
