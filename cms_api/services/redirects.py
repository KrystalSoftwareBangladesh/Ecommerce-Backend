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
"""
from wagtail.contrib.redirects.models import Redirect
from wagtail.log_actions import log

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
