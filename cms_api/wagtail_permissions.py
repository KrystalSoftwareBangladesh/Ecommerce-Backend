# cms_api/wagtail_permissions.py
"""Wagtail Admin authorization, backed by the existing CMS RBAC
(docs/cms-architecture.md AD-11, Phase 5A).

Wagtail's native page permissions (``wagtail.models.
GroupPagePermission``) are a genuinely separate system from this
project's RBAC: permission is granted to a Django ``Group``, scoped to
a specific page in the tree, using Wagtail's own auto-generated
codenames (``add_page``/``change_page``/``publish_page``, all on the
*base* ``wagtailcore.Page`` content type, never ``cms_api.CmsPage``).
Confirmed empirically before writing any of this: a staff user granted
every relevant ``cms_api`` permission still got ``False`` from every
``page_permission_policy.user_has_permission(user, action)`` call, and
``explorable_instances(user).count() == 0`` — nothing here is wired up
by Django's own `add_X`/`change_X` auto-creation, because Wagtail's
page-tree policy never looks at those codenames.

Snippets (``CmsSection``) are closer: standard CRUD already goes
through ``ModelPermissionPolicy``, which *does* check the same
``add_cmssection``/``change_cmssection``/``delete_cmssection``/
``view_cmssection`` codenames our RBAC already grants. Only the
custom publish/unpublish actions diverge, because Wagtail constructs
``f"{action}_{model._meta.model_name}"`` (``publish_cmssection``, no
underscore before "section") — a codename this project never declared
(ours is ``publish_cms_section``) and that is therefore held by no one
but a superuser.

No ``GroupPagePermission`` row and no duplicate Wagtail-style
codename (``publish_cmspage``, ``publish_cmssection``, ...) is ever
created here — every check below reads the existing ``cms_api``
permissions through ``user.has_perm()`` only, so it goes through
whatever authentication backends are configured (including
``user_api.backends.EmailOrUsernameBackend``'s company-wise role
assignment) exactly like the DRF API already does.
"""
from types import SimpleNamespace

from wagtail.permission_policies import ModelPermissionPolicy
from wagtail.permission_policies.pages import PagePermissionPolicy
from wagtail.snippets.views.snippets import SnippetViewSet
from wagtail.snippets.views.snippets import UnpublishView as _BaseUnpublishView

PAGE_APP_LABEL = "cms_api"

# Wagtail action name -> cms_api.CmsPage permission codename.
# lock/unlock have no dedicated spec permission (docs/cms-
# architecture.md §8 lists none); both are mapped to change_cmspage
# as the closest existing equivalent — an explicit assumption, not a
# spec requirement, called out in the Phase 5A report.
PAGE_ACTION_CODENAMES = {
    "add": "add_cmspage",
    "view": "view_cmspage",
    "change": "change_cmspage",
    "delete": "delete_cmspage",
    "publish": "publish_cms_page",
    "unpublish": "unpublish_cms_page",
    "lock": "change_cmspage",
    "unlock": "change_cmspage",
    "bulk_delete": "delete_cmspage",
}

# Codenames that stand in for a held cms_api permission when feeding
# Wagtail's *default* PagePermissionTester (used for any Page that is
# not a CmsPage — in practice only the invisible tree root, depth=1,
# which is a plain wagtailcore.Page). That tester parses codenames as
# f"{action}_page" (see wagtail.models.pages.PagePermissionTester.
# __init__: `codename.rsplit("_", maxsplit=1)[0]`), so the fake
# objects below must use Wagtail's own naming, not ours — they are
# never saved anywhere, only read by that one comprehension.
_ROOT_FALLBACK_CODENAMES = {
    "add_cmspage": "add_page",
    "change_cmspage": "change_page",
    "publish_cms_page": "publish_page",
}


class CmsPagePermissionPolicy(PagePermissionPolicy):
    """Installed in place of the global ``wagtail.permissions.
    page_permission_policy`` singleton (see ``cms_api.apps.ready``) —
    every Wagtail Admin view that imports that name, whether as a
    module-level binding or a class attribute, ends up pointing at
    this same object, because it is the *same instance* with its
    class swapped, not a new object other imports would miss.
    """

    def _user_has_actions(self, user, actions):
        if not user.is_active:
            return False
        if user.is_superuser:
            return True
        if not user.is_staff:
            return False
        codenames = {
            PAGE_ACTION_CODENAMES.get(action, f"{action}_cmspage")
            for action in actions
        }
        return any(
            user.has_perm(f"{PAGE_APP_LABEL}.{codename}")
            for codename in codenames
        )

    def user_has_permission(self, user, action):
        return self._user_has_actions(user, {action})

    def user_has_any_permission(self, user, actions):
        return self._user_has_actions(user, actions)

    def user_has_permission_for_instance(self, user, action, instance):
        return self.user_has_permission(user, action)

    def user_has_any_permission_for_instance(self, user, actions, instance):
        return self.user_has_any_permission(user, actions)

    def instances_user_has_any_permission_for(self, user, actions):
        if not user.is_active:
            return self.model._default_manager.none()
        if user.is_superuser:
            return self.model._default_manager.all()
        if not user.is_staff:
            return self.model._default_manager.none()
        # "view" alone grants read-only explorer access; it never
        # appears in Wagtail's own default action set for the
        # explorer (wagtail.permission_policies.pages.
        # PagePermissionPolicy.explorable_instances), so a view-only
        # user must be checked for explicitly here.
        if self._user_has_actions(
            user, set(actions) | {"view"},
        ):
            return self.model._default_manager.all()
        return self.model._default_manager.none()

    def explorable_instances(self, user):
        base_queryset = self._base_queryset_for_user(user)
        if base_queryset is not None:
            return base_queryset
        return self.instances_user_has_any_permission_for(
            user,
            {"add", "change", "publish", "lock", "unlock", "bulk_delete"},
        )

    def get_all_permissions_for_user(self, user):
        """Fallback permission source for the *default*
        ``PagePermissionTester`` (only ever used for a ``Page`` that
        is not a ``CmsPage`` — i.e. the invisible tree root). Returns
        synthetic, never-persisted permission-like objects so "add a
        new top-level page" works for a ``cms_api.add_cmspage``
        holder without any ``GroupPagePermission`` row existing.
        """
        if not user.is_active or user.is_superuser:
            return []
        root = self.model._default_manager.filter(depth=1).first()
        if root is None:
            return []
        fakes = []
        for our_codename, fake_codename in _ROOT_FALLBACK_CODENAMES.items():
            if user.has_perm(f"{PAGE_APP_LABEL}.{our_codename}"):
                fakes.append(
                    SimpleNamespace(
                        permission=SimpleNamespace(codename=fake_codename),
                        page=root,
                    )
                )
        if user.has_perm(f"{PAGE_APP_LABEL}.change_cmspage"):
            for fake_codename in ("lock_page", "unlock_page"):
                fakes.append(
                    SimpleNamespace(
                        permission=SimpleNamespace(codename=fake_codename),
                        page=root,
                    )
                )
        return fakes


class CmsPagePermissionTester:
    """Replaces Wagtail's native ``PagePermissionTester`` for
    ``CmsPage`` (installed via ``CmsPage.permissions_for_user``,
    which Wagtail's own ``Page.permissions_for_user`` docstring
    explicitly documents as overridable per specific page class).

    Deliberately not a subclass of ``PagePermissionTester``: several
    of its methods bake in semantics that don't hold for this
    project's distinct permissions — ``can_delete()`` succeeds on
    ``"change"`` alone (no dedicated delete permission in Wagtail's
    own model), and ``can_unpublish()`` checks the same ``"publish"``
    flag as ``can_publish()`` (Wagtail has no separate unpublish
    permission natively). This project has ``delete_cmspage`` and
    ``unpublish_cms_page`` as distinct permissions from
    ``change_cmspage``/``publish_cms_page``, so each method below
    checks its own exact codename instead of reusing another action's
    check.
    """

    def __init__(self, user, page):
        self.user = user
        self.page = page
        self.page_is_root = page.depth == 1

    def _has(self, codename):
        if not self.user.is_active:
            return False
        if self.user.is_superuser:
            return True
        if not self.user.is_staff:
            return False
        return self.user.has_perm(f"{PAGE_APP_LABEL}.{codename}")

    def user_has_lock(self):
        return self.page.locked_by_id == self.user.pk

    def page_locked(self):
        lock = self.page.get_lock()
        return bool(lock and lock.for_user(self.user))

    def can_add_subpage(self):
        if not self.user.is_active:
            return False
        specific_class = self.page.specific_class
        if specific_class is None:
            return False
        creatable_subpage_models = specific_class.creatable_subpage_models()
        if not any(
            subpage_model.can_create_at(self.page)
            for subpage_model in creatable_subpage_models
        ):
            return False
        return self._has("add_cmspage")

    def can_edit(self):
        if not self.user.is_active or self.page_is_root:
            return False
        return self._has("change_cmspage")

    def can_delete(self, ignore_bulk=False):
        if not self.user.is_active or self.page_is_root:
            return False
        return self._has("delete_cmspage")

    def can_unpublish(self):
        if not self.user.is_active:
            return False
        if (not self.page.live) or self.page_is_root:
            return False
        if self.page_locked():
            return False
        return self._has("unpublish_cms_page")

    def can_publish(self):
        if not self.user.is_active or self.page_is_root:
            return False
        return self._has("publish_cms_page")

    def can_submit_for_moderation(self):
        return (
            not self.page_locked()
            and self.page.has_workflow
            and not self.page.workflow_in_progress
        )

    def can_set_view_restrictions(self):
        return self.can_publish()

    def can_unschedule(self):
        return self.can_publish()

    def can_lock(self):
        if self.user.is_superuser:
            return True
        current_workflow_task = self.page.current_workflow_task
        if current_workflow_task:
            return current_workflow_task.user_can_lock(self.page, self.user)
        return self._has("change_cmspage")

    def can_unlock(self):
        if self.user.is_superuser:
            return True
        if self.user_has_lock():
            return True
        current_workflow_task = self.page.current_workflow_task
        if current_workflow_task:
            return current_workflow_task.user_can_unlock(self.page, self.user)
        return self._has("change_cmspage")

    def can_publish_subpage(self):
        if not self.user.is_active:
            return False
        specific_class = self.page.specific_class
        if (
            specific_class is None
            or not specific_class.creatable_subpage_models()
        ):
            return False
        return self._has("publish_cms_page")

    def can_reorder_children(self):
        if not self.user.is_active:
            return False
        return self._has("publish_cms_page")

    def can_move(self):
        return self.can_delete(ignore_bulk=True) and self._has("add_cmspage")

    def can_copy(self):
        return self.can_edit()

    def can_move_to(self, destination):
        if self.page == destination or destination.is_descendant_of(self.page):
            return False
        if (not self.page.is_child_of(destination)) and (
            not self.page.specific.can_move_to(destination)
        ):
            return False
        if not self.user.is_active:
            return False
        if self.user.is_superuser:
            return True
        if not self.can_move():
            return False

        destination_perms = destination.permissions_for_user(self.user)
        if not getattr(destination_perms, "_has", None):
            return False
        if not destination_perms._has("add_cmspage"):
            return False

        has_live_descendant = self.page.get_descendants().filter(
            live=True,
        ).exists()
        if self.page.live or has_live_descendant:
            return destination_perms._has("publish_cms_page")
        return True

    def can_copy_to(self, destination, recursive=False):
        if not self.can_copy():
            return False
        if recursive and (
            self.page == destination or destination.is_descendant_of(self.page)
        ):
            return False
        if not self.user.is_active:
            return False
        if not self.page.specific_class.can_create_at(destination):
            return False
        if self.user.is_superuser:
            return True

        destination_perms = destination.permissions_for_user(self.user)
        if not hasattr(destination_perms, "can_add_subpage"):
            return False
        return destination_perms.can_add_subpage()

    def can_view_revisions(self):
        return not self.page_is_root


# --- CmsSection (snippet) ----------------------------------------------
#
# Standard CRUD already works unmodified: Wagtail's snippet views use
# ModelPermissionPolicy, which checks add_cmssection/change_cmssection/
# delete_cmssection/view_cmssection — the same codenames Django's own
# auto-creation gives this model, already granted by the existing RBAC.
# Only the custom lifecycle actions diverge, because Wagtail builds the
# codename as f"{action}_{model_name}" ("publish_cmssection", no
# underscore before "section") — never declared here (ours is
# publish_cms_section) and therefore held by no one but a superuser.
# Confirmed empirically: a staff user granted publish_cms_section still
# got False from the default policy's user_has_permission(user,
# "publish") before this fix.

SECTION_APP_LABEL = "cms_api"

# lock/unlock have no dedicated spec permission for sections either;
# mapped to change_cmssection as the closest existing equivalent, the
# same assumption made for pages above.
SECTION_ACTION_CODENAMES = {
    "publish": "publish_cms_section",
    "unpublish": "unpublish_cms_section",
    "lock": "change_cmssection",
    "unlock": "change_cmssection",
}


class CmsSectionPermissionPolicy(ModelPermissionPolicy):
    """Standard actions (add/view/change/delete) are left to
    ``ModelPermissionPolicy``'s own behaviour, unmodified, since they
    already check the correct codenames. Only the actions in
    ``SECTION_ACTION_CODENAMES`` are redirected to this project's
    distinct permissions."""

    def user_has_permission(self, user, action):
        codename = SECTION_ACTION_CODENAMES.get(action)
        if codename is None:
            return super().user_has_permission(user, action)
        if not user.is_active:
            return False
        if user.is_superuser:
            return True
        if not user.is_staff:
            return False
        return user.has_perm(f"{SECTION_APP_LABEL}.{codename}")


class CmsSectionUnpublishView(_BaseUnpublishView):
    """Wagtail's own ``UnpublishView.permission_required = "publish"``
    (``wagtail/snippets/views/snippets.py``) — unpublish is gated on
    the *same* action string as publish, so a policy-level redirect of
    "publish" alone would let a ``publish_cms_section`` holder (and
    only that holder) unpublish too. Overridden here to check
    ``unpublish_cms_section`` directly, independently of whatever the
    policy does for "publish"."""

    def user_has_permission(self, permission):
        user = self.request.user
        if not user.is_active:
            return False
        if user.is_superuser:
            return True
        if not user.is_staff:
            return False
        return user.has_perm(f"{SECTION_APP_LABEL}.unpublish_cms_section")


class CmsSectionSnippetViewSet(SnippetViewSet):
    """Registered in place of the default ``SnippetViewSet`` for
    ``CmsSection`` (``cms_api/wagtail_hooks.py``:
    ``register_snippet(CmsSection, viewset=CmsSectionSnippetViewSet)``
    — Wagtail's own documented per-model customization point)."""

    unpublish_view_class = CmsSectionUnpublishView

    @property
    def permission_policy(self):
        return CmsSectionPermissionPolicy(self.model)
