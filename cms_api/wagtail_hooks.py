# cms_api/wagtail_hooks.py
"""Wagtail registrations for the CMS (docs/cms-architecture.md).

Product, Category and Brand are registered as snippets because the
section registry's chooser blocks (product_collection,
product_slider, category_collection, brand_collection) use
``SnippetChooserBlock``, which requires snippet models to resolve
their choosers and validate content.

Side effect (reported in the Phase 1 report): these three models
appear in the Wagtail admin "Snippets" menu. That admin surface is
Phase 5's concern; registration here is for the content pipeline.
"""
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _

from rest_framework.exceptions import ValidationError

from wagtail import hooks
from wagtail.admin import messages
from wagtail.models import ReferenceIndex
from wagtail.snippets.models import register_snippet

from category_api.models import Category
from cms_api.forms import CmsPageForm, format_validation_error
from cms_api.models import CmsPage, CmsSection
from cms_api.services.pages import (
    _validate_reserved_path,
    nav_item_dependencies,
)
from cms_api.wagtail_permissions import CmsSectionSnippetViewSet
from product_api.models import Brand, Product

# CmsSectionSnippetViewSet (Phase 5A, docs/cms-architecture.md AD-11)
# redirects the snippet's publish/unpublish/lock/unlock actions to the
# existing cms_api permissions instead of Wagtail's auto-generated
# codenames; standard CRUD is unaffected.
register_snippet(CmsSection, viewset=CmsSectionSnippetViewSet)
register_snippet(Product)
register_snippet(Category)
register_snippet(Brand)

# Track CmsSection as a reference source so its product/category/
# brand references are recorded in the ReferenceIndex (delete guards
# on those entities stay accurate).
ReferenceIndex.register_model(CmsSection)


@hooks.register("register_log_actions")
def register_cms_log_actions(actions):
    """Register log actions not provided by Wagtail core.

    ``wagtail.create``/``wagtail.edit``/``wagtail.delete`` exist in
    core; the ``cms_api.*`` actions cover CMS service writes and the
    archive operation, which have no Wagtail-native action.
    """
    actions.register_action(
        "cms_api.create", _("Create"), _("Created")
    )
    actions.register_action(
        "cms_api.update", _("Update"), _("Updated")
    )
    actions.register_action(
        "cms_api.archive", _("Archive"), _("Archived")
    )
    actions.register_action(
        "cms_api.restore", _("Restore"), _("Restored")
    )
    actions.register_action(
        "cms_api.rollback", _("Rollback"), _("Rolled back")
    )
    actions.register_action(
        "cms_api.redirect.create",
        _("Create redirect"),
        _("Created redirect"),
    )
    actions.register_action(
        "cms_api.navigation.reorder",
        _("Reorder navigation items"),
        _("Reordered navigation items"),
    )


# --- business rules in the admin (Phase 5B) -------------------------
#
# The DRF services enforce reserved paths, navigation references and
# the reference guard on delete; Wagtail Admin publishes/deletes never
# touch those services, so the same rules are enforced here.

# Wagtail assigns Page.base_form_class = WagtailAdminPageForm the same
# way (wagtail/admin/panels/page_utils.py); the form class must be a
# WagtailAdminPageForm subclass (wagtail/admin/checks.py).
CmsPage.base_form_class = CmsPageForm


@hooks.register("before_publish_page")
def guard_reserved_paths_on_publish(request, page):
    """Veto an admin publish whose resulting URL path is reserved.

    The slug-form check does not cover every path to live (bulk
    publish, workflow approval, a page moved under a reserved
    parent), so the rule is re-checked at publish time. Returning an
    ``HttpResponse`` vetoes the publish — Wagtail's own hook
    contract; ``None`` lets it proceed.
    """
    try:
        _validate_reserved_path(page.url_path)
    except ValidationError as exc:
        messages.error(request, format_validation_error(exc))
        return redirect("wagtailadmin_pages:edit", page.id)
    return None


@hooks.register("before_delete_page")
def guard_nav_referenced_pages_on_delete(request, page):
    """Veto an admin delete of a page (or subtree) that navigation
    items point at.

    ``CmsNavigationItem.page`` is a ``PROTECT`` foreign key (docs
    §5.5): without this guard the admin delete raises a raw
    ``ProtectedError`` (a 500) for a descendant reference. The DRF
    ``delete_page`` guard is never acknowledgeable, so neither is
    this one — the item must be removed or repointed first. The hook
    runs on both the confirmation page and the POST, so a delete
    never starts that cannot finish.
    """
    nav_dependencies = nav_item_dependencies(page)
    if nav_dependencies:
        items = ", ".join(
            dependency["object"] for dependency in nav_dependencies
        )
        messages.error(
            request,
            "Cannot delete this page: it or its subtree is "
            "referenced by navigation items (%s). Remove or "
            "repoint them first." % items,
        )
        return redirect("wagtailadmin_pages:edit", page.id)
    return None
