# cms_api/forms.py
"""Wagtail Admin form customizations (docs/cms-architecture.md
Phase 5B).

Reserved-path validation (``CMS_RESERVED_PATHS``) already runs in the
DRF services on create, slug change and rollback. Wagtail Admin
publishes never touch those services, so the same rule is enforced
here — in the page form's ``clean_slug`` — plus a publish-time hook
guard for paths that never pass through a form at all (see
``cms_api/wagtail_hooks.py``).
"""
from django import forms

from rest_framework.exceptions import ValidationError

from wagtail.admin.forms.pages import WagtailAdminPageForm

from cms_api.services.pages import (
    _prospective_url_path,
    _validate_reserved_path,
)


def format_validation_error(exc):
    """One readable message from a DRF ``ValidationError`` raised by
    a service, for display through Wagtail's message framework."""
    detail = exc.detail
    while isinstance(detail, dict):
        detail = next(iter(detail.values()))
    if isinstance(detail, (list, tuple)):
        detail = detail[0]
    return str(detail)


class CmsPageForm(WagtailAdminPageForm):
    """Reserved paths cannot be published through the admin either.

    Mirrors ``services/pages.py``: the rule is checked only when the
    slug actually changes (or on add), never on a save that leaves
    the path untouched. ``WagtailAdminPageForm`` has no
    ``clean_slug`` of its own, so there is no super() call here.
    """

    def clean_slug(self):
        slug = self.cleaned_data["slug"]
        instance = self.instance
        if instance.pk and slug == instance.slug:
            return slug
        parent = self.parent_page
        if parent is None and instance.pk:
            parent = instance.get_parent()
        if parent is not None:
            try:
                _validate_reserved_path(
                    _prospective_url_path(parent, slug)
                )
            except ValidationError as exc:
                raise forms.ValidationError(format_validation_error(exc))
        return slug
