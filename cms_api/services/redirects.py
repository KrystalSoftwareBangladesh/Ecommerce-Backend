# cms_api/services/redirects.py
"""Slug-change redirects for CMS pages (docs/cms-architecture.md
AD-8, §9, §12).

A redirect's target is always the page itself (``redirect_page``),
resolved at lookup time through ``published_url_path``, never another
redirect's ``old_path``. Every historical path a page has ever held
therefore resolves straight to its *current* canonical URL, with no
transitive chains, and a rename back to an earlier path simply drops
the now-stale redirect rather than looping.

Redirects are created only from here, at publish time (``publish_page``,
``rollback_page``, the scheduled sweep in ``services/scheduling.py``) —
never from a draft-only slug edit. Wagtail's own
``WAGTAILREDIRECTS_AUTO_CREATE`` signal handler, which would otherwise
fire on every ``Page.save()`` where the slug differs from the stored
row (including a draft edit via ``update_page``), is disabled in
settings for exactly this reason.

Wagtail Admin publishes (the edit/create publish button, bulk
publish, workflow approval) never call the helpers below explicitly,
so redirects for those are created from signals instead: a ``pre_save``
receiver snapshots the published paths at the moment a publish flips
``live_revision`` (the database row is still pre-publish there, the
same snapshot ``services/pages.py`` takes explicitly before its
actions) and a ``page_published`` receiver turns that snapshot into
redirects. The DRF services and the scheduled sweep keep creating
their redirects explicitly, with the acting user, and suppress the
signal path (``suppress_signal_redirects``) so exactly one set of
redirects — and one ``cms_api.redirect.create`` log entry per moved
path — exists however a page goes live (Phase 5B).
"""
import threading
from contextlib import contextmanager

from django.db.models.signals import pre_save

from wagtail.contrib.redirects.models import Redirect
from wagtail.log_actions import log
from wagtail.signals import page_published

from cms_api.models import CmsPage
from cms_api.services.paths import published_url_path


def _normalise(path):
    return Redirect.normalise_path(path)


def snapshot_published_paths(page):
    """Capture a page's published path and its live descendants'
    published paths, before a publish action may change them."""
    old_path = published_url_path(page) if page.pk else None
    descendants = list(page.get_descendants().live()) if page.pk else []
    old_descendant_paths = {
        descendant.pk: published_url_path(descendant)
        for descendant in descendants
    }
    return old_path, descendants, old_descendant_paths


def create_slug_redirect(*, page, old_path, new_path, user=None):
    """Create/update a redirect from ``old_path`` to ``page``.

    A redirect already sitting at ``new_path`` (e.g. a page renamed
    back to an earlier slug it once redirected away from) is removed
    first: that path is now the page's own live canonical URL, not a
    redirect source, so it would otherwise be both at once.
    """
    old_norm = _normalise(old_path)
    new_norm = _normalise(new_path)
    if old_norm == new_norm:
        return None
    Redirect.objects.filter(
        old_path=new_norm, site__isnull=True,
    ).delete()
    redirect, _created = Redirect.objects.update_or_create(
        old_path=old_norm,
        site=None,
        defaults={
            "redirect_page": page,
            "redirect_page_route_path": "",
            "redirect_link": "",
            "is_permanent": True,
            "automatically_created": True,
        },
    )
    log(
        instance=page,
        action="cms_api.redirect.create",
        user=user,
        data={
            "redirect": {"old_path": old_norm, "new_path": new_norm},
        },
    )
    return redirect


def create_redirects_for_published_change(
    *, page, old_path, descendants, old_descendant_paths, user=None,
):
    """After a publish action has run (and ``page`` refreshed from
    the database), create redirects for the page and any live
    descendant whose published path moved."""
    created = 0
    if old_path is not None:
        new_path = published_url_path(page)
        if create_slug_redirect(
            page=page, old_path=old_path, new_path=new_path, user=user,
        ):
            created += 1
    for descendant in descendants:
        old_descendant_path = old_descendant_paths.get(descendant.pk)
        if old_descendant_path is None:
            continue
        new_descendant_path = published_url_path(descendant)
        if create_slug_redirect(
            page=descendant,
            old_path=old_descendant_path,
            new_path=new_descendant_path,
            user=user,
        ):
            created += 1
    return created


def resolve_redirect_path(path):
    """Old path -> current canonical path, or ``None`` when there is
    no redirect, or its target page is no longer live/archived."""
    normalised = _normalise(path)
    redirect = Redirect.objects.filter(
        old_path=normalised, site__isnull=True,
    ).select_related("redirect_page").first()
    if redirect is None:
        return None
    if redirect.redirect_page_id:
        target = redirect.redirect_page.specific
        if not target.live or getattr(
            target, "archived_at", None,
        ) is not None:
            return None
        return published_url_path(target)
    return redirect.redirect_link or None


# --- signal-based coverage (Phase 5B) -------------------------------
#
# Wagtail Admin publishes never call the helpers above explicitly, so
# redirects for those are created from signals: the ``pre_save``
# receiver below snapshots the published paths at the moment a publish
# flips ``live_revision`` (the database row is still pre-publish
# there), and the ``page_published`` receiver turns that snapshot into
# redirects. The DRF services and the scheduled sweep keep creating
# their redirects explicitly, with the acting user, and suppress this
# signal path so exactly one set of redirects — and one
# ``cms_api.redirect.create`` log entry per moved path — exists
# however a page goes live.

_thread_state = threading.local()


def _pending_captures():
    pending = getattr(_thread_state, "pending_captures", None)
    if pending is None:
        pending = {}
        _thread_state.pending_captures = pending
    return pending


@contextmanager
def suppress_signal_redirects():
    """Nestable. Silences only the ``page_published`` receiver, so a
    caller that creates its own redirects explicitly (with the acting
    user) never gets a second, duplicate set from the signal path."""
    was_suppressed = getattr(_thread_state, "suppressed", False)
    _thread_state.suppressed = True
    try:
        yield
    finally:
        _thread_state.suppressed = was_suppressed


def capture_published_path_change(sender, instance, **kwargs):
    """``pre_save`` on ``CmsPage``: when this save is a publish (it
    flips ``live_revision_id``), snapshot the *old* published paths
    from the pre-save database row."""
    if kwargs.get("raw") or instance.pk is None or not instance.live:
        return
    if not instance.live_revision_id:
        return
    row = sender._default_manager.filter(pk=instance.pk).first()
    if row is None or row.live_revision_id == instance.live_revision_id:
        return
    _pending_captures()[instance.pk] = snapshot_published_paths(row)


def create_redirects_on_page_published(sender, instance, **kwargs):
    """``page_published`` on ``CmsPage``: turn the captured snapshot
    into redirects, unless the caller opted out of the signal path."""
    pending = _pending_captures().pop(instance.pk, None)
    if pending is None:
        return
    if getattr(_thread_state, "suppressed", False):
        return
    old_path, descendants, old_descendant_paths = pending
    create_redirects_for_published_change(
        page=instance,
        old_path=old_path,
        descendants=descendants,
        old_descendant_paths=old_descendant_paths,
    )


def connect_redirect_receivers():
    pre_save.connect(
        capture_published_path_change,
        sender=CmsPage,
        dispatch_uid="cms_api.capture_published_path_change",
    )
    page_published.connect(
        create_redirects_on_page_published,
        dispatch_uid="cms_api.create_redirects_on_page_published",
    )
