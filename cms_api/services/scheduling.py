# cms_api/services/scheduling.py
"""Scheduled publish/unpublish sweep (docs/cms-architecture.md §12,
Phase 0 §13.2).

The actual sweep is Wagtail's own ``publish_scheduled`` management
command, which covers ``go_live_at``/``expire_at`` for ``Page`` and
every ``DraftStateMixin`` model (sections included) and already uses
the Page-specific publish/unpublish actions internally, so
``page_published``/``page_unpublished`` fire correctly for it. This
service only adds the one thing that command has no hook for: a
``CmsPage`` whose scheduled revision goes live with a different
published path needs the same slug-change redirect an explicit API
publish creates (AD-8, §9). The published path of every pending
``CmsPage`` revision is snapshotted before the command runs, then
diffed against the refreshed page afterwards.
"""
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.utils import timezone

from wagtail.models import Revision

from cms_api.models import CmsPage
from cms_api.services.redirects import (
    create_redirects_for_published_change,
    snapshot_published_paths,
)


def run_scheduled_publishing():
    """Run Wagtail's scheduled sweep; return counters for the task."""
    now = timezone.now()
    content_type = ContentType.objects.get_for_model(
        CmsPage, for_concrete_model=False,
    )
    pending_ids = list(
        Revision.objects.filter(
            content_type=content_type,
            approved_go_live_at__lt=now,
        ).values_list("object_id", flat=True)
    )
    snapshots = {}
    for object_id in pending_ids:
        page = CmsPage.objects.filter(pk=object_id).first()
        if page is not None:
            snapshots[int(object_id)] = snapshot_published_paths(page)

    call_command("publish_scheduled")

    redirects_created = 0
    for object_id, (
        old_path, descendants, old_descendant_paths,
    ) in snapshots.items():
        page = CmsPage.objects.filter(pk=object_id).first()
        if page is None:
            continue
        redirects_created += create_redirects_for_published_change(
            page=page,
            old_path=old_path,
            descendants=descendants,
            old_descendant_paths=old_descendant_paths,
            user=None,
        )
    return {
        "pages_swept": len(snapshots),
        "redirects_created": redirects_created,
    }
