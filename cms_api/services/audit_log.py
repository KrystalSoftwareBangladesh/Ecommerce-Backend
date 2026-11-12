# cms_api/services/audit_log.py
"""Read-only audit-log API (docs/cms-architecture.md §6, §11, AD-10).

Wagtail already stores every logged action in one of two tables —
``PageLogEntry`` (pages) and ``ModelLogEntry`` (everything else,
registered as the catch-all logger for *any* model by Wagtail core
itself) — so this reuses them directly rather than introducing a
second audit-log storage system. The two cannot be combined with a
single queryset: ``PageLogEntry.object_id`` is a Python property
(``page_id``), not a database column, so each source is queried and
filtered separately, then merged and sorted in Python. Both filters
run *before* the merge, and a date window is always applied (default
90 days, capped at 365), so the in-memory set is bounded by the
filtered window, never by the full history of either table.

The content-type allowlist below is deliberately explicit: ``Product``,
``Category`` and ``Brand`` are registered as Wagtail snippets for
chooser-block support (``cms_api/wagtail_hooks.py``) and would also
log to ``ModelLogEntry`` if ever edited through Wagtail Admin — an
unfiltered query would leak that unrelated activity into "CMS
activity."
"""
from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from wagtail.documents.models import Document
from wagtail.images.models import Image
from wagtail.models import ModelLogEntry, PageLogEntry

from cms_api.models import (
    CmsMediaConfig,
    CmsNavigationItem,
    CmsNavigationMenu,
    CmsPage,
    CmsSection,
)

DEFAULT_WINDOW_DAYS = 90
MAX_WINDOW_DAYS = 365

PAGE_CONTENT_TYPE_KEY = "cmspage"

# Lowercase content-type key -> model, matching ContentType.model.
# CmsPage is handled separately (PageLogEntry), listed here only so
# it is a valid value for the content_type filter too.
CMS_AUDIT_CONTENT_TYPES = {
    PAGE_CONTENT_TYPE_KEY: CmsPage,
    "cmssection": CmsSection,
    "cmsnavigationmenu": CmsNavigationMenu,
    "cmsnavigationitem": CmsNavigationItem,
    "image": Image,
    "document": Document,
    "cmsmediaconfig": CmsMediaConfig,
}


def _model_content_types(keys):
    return [
        ContentType.objects.get_for_model(
            CMS_AUDIT_CONTENT_TYPES[key], for_concrete_model=False,
        )
        for key in keys
        if key != PAGE_CONTENT_TYPE_KEY
    ]


def resolve_audit_log_window(start_date=None, end_date=None):
    """Clamp the requested range: default 90 days, capped at 365."""
    now = timezone.now()
    if end_date is None:
        end_date = now
    if start_date is None:
        start_date = end_date - timedelta(days=DEFAULT_WINDOW_DAYS)
    if end_date - start_date > timedelta(days=MAX_WINDOW_DAYS):
        start_date = end_date - timedelta(days=MAX_WINDOW_DAYS)
    return start_date, end_date


def _actor(entry):
    if entry.user_id is None:
        return None
    if entry.user is None:
        # The user row itself no longer exists (DO_NOTHING FK).
        return None
    return entry.user.get_username()


def _page_entry(entry):
    return {
        "actor": _actor(entry),
        "actor_id": entry.user_id,
        "action": entry.action,
        "model": CmsPage._meta.label,
        "object_id": entry.page_id,
        "object": entry.label,
        "timestamp": entry.timestamp,
        "data": entry.data,
    }


def _model_entry(entry):
    model_class = entry.content_type.model_class()
    return {
        "actor": _actor(entry),
        "actor_id": entry.user_id,
        "action": entry.action,
        "model": (
            model_class._meta.label
            if model_class else entry.content_type.model
        ),
        "object_id": entry.object_id,
        "object": entry.label,
        "timestamp": entry.timestamp,
        "data": entry.data,
    }


def list_audit_log_entries(
    *, start_date=None, end_date=None, action=None, content_type=None,
):
    """Merged, descending-timestamp list of audit-log entries for
    every CMS-owned content type, within the resolved date window."""
    start_date, end_date = resolve_audit_log_window(start_date, end_date)

    keys = (
        [content_type] if content_type else list(CMS_AUDIT_CONTENT_TYPES)
    )
    include_pages = PAGE_CONTENT_TYPE_KEY in keys

    entries = []

    if include_pages:
        page_qs = PageLogEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(
                CmsPage, for_concrete_model=False,
            ),
            timestamp__gte=start_date,
            timestamp__lte=end_date,
        ).select_related("user")
        if action:
            page_qs = page_qs.filter(action=action)
        entries.extend(_page_entry(e) for e in page_qs.iterator())

    model_content_types = _model_content_types(keys)
    if model_content_types:
        model_qs = ModelLogEntry.objects.filter(
            content_type__in=model_content_types,
            timestamp__gte=start_date,
            timestamp__lte=end_date,
        ).select_related("user", "content_type")
        if action:
            model_qs = model_qs.filter(action=action)
        entries.extend(_model_entry(e) for e in model_qs.iterator())

    entries.sort(key=lambda entry: entry["timestamp"], reverse=True)
    return entries
