# cms_api/services/cache.py
"""Public-response caching for the CMS (docs/cms-architecture.md
§10, AD-12, Phase 5C).

Pattern: a registry key per *group* holds the set of literal cache
keys currently tagged under it (mirrors ``category_api/services/
cache.py``); invalidating a group deletes every key in it plus the
registry entry. This works identically on the "cms" alias whether it
is Redis (deployments) or ``LocMemCache``/``DummyCache`` (dev/tests):
neither of the latter two implements ``delete_pattern()``, so pattern
deletes are never used.

Groups:
- ``page:<id>`` — one page's public detail payload.
- ``pages-list`` — the public page list (``GET /public/pages/`` with
  no ``path``).
- ``sitemap`` — the sitemap response.
- ``navigation:<key>`` — one navigation menu's public tree.
``section-types`` has no group: its content is derived entirely from
code (``cms_api.sections.registry``), so nothing ever invalidates it;
it expires only via its own TTL (e.g. after a deploy changes the
registry).

Invalidation sources, verified against the installed Wagtail 7.4.4
(not assumed — see the Phase 5C audit report):
- ``wagtail.signals.page_published``/``page_unpublished`` fire with
  ``sender=object.specific_class`` for *every* page publish/unpublish
  path: the DRF services, Wagtail Admin, the scheduled
  ``publish_scheduled`` sweep (which operates on the base ``Page``
  queryset but still resolves the specific class/instance before
  sending), and rollback (which reuses the same publish action). One
  receiver on each, filtered to ``sender=CmsPage``, covers all of
  them — no per-pathway invalidation call is needed in
  ``services/pages.py``.
- ``wagtail.signals.post_page_move`` fires on a Wagtail Admin page
  tree move/reorder, which can change a page's (and its live
  descendants') published path without any publish/unpublish at all
  (docs/cms-architecture.md, Phase 5B note: "the move itself is
  accepted" even though publish-time still guards reserved paths).
- ``wagtail.signals.published``/``unpublished`` are Wagtail's
  *generic* DraftStateMixin signals (there is no ``snippet_published``
  in this Wagtail version — docs/cms-architecture.md §10 named one
  that does not exist). ``CmsSection`` publish/unpublish — from the
  DRF services, the Wagtail Admin snippet viewset, or scheduled
  expiry — fires these with ``sender=CmsSection``, since
  ``PublishRevisionAction``/``UnpublishAction`` (the section actions)
  send only the generic signal, never a page-specific one.
  ``PublishPageRevisionAction``/``UnpublishPageAction`` *also* send
  the generic signal for pages (``sender=CmsPage``), so connecting
  the generic receiver with ``sender=CmsSection`` only is what keeps
  a page publish from invalidating through two receivers at once.

Not covered by any Wagtail signal — invalidated explicitly inside the
relevant service, wrapped in the caller's existing
``transaction.atomic`` via ``transaction.on_commit``:
- Page archive/restore/permanent delete (``services/pages.py``).
- Section archive/soft-delete (``services/cms_section.py``).
- Every navigation menu/item write (``services/navigation.py`` —
  plain Django models, no Wagtail revisions or signals at all).

Known limitation (see the Phase 5C final report): a global section's
referencing pages are found via ``ReferenceIndex``, which indexes a
page's *current* (possibly draft) composition rows, not its published
revision's content. A page whose live revision still embeds a section
that the page's own unpublished draft has since dropped would be
missed by this fan-out. The safety-net TTL bounds that one gap; it is
not a case the ``ReferenceIndex`` approach the spec calls for can
close without indexing revision content, which is out of this
phase's scope.
"""
from django.conf import settings
from django.core.cache import caches
from django.db import transaction

from wagtail.models import Page, ReferenceIndex

CACHE_ALIAS = "cms"
PREFIX = "cms"

PAGES_LIST_GROUP = "pages-list"
SITEMAP_GROUP = "sitemap"


def _cache():
    # Resolved fresh on every call (never bound to a module-level
    # name) so tests can swap the "cms" alias with
    # ``override_settings`` and have it take effect immediately.
    return caches[CACHE_ALIAS]


def _ttl():
    return settings.CMS_PUBLIC_CACHE_TTL


# --- keys and groups -------------------------------------------------

def pages_list_key():
    return f"{PREFIX}:pages:list"


def sitemap_key():
    return f"{PREFIX}:sitemap"


def page_detail_key(page_id):
    return f"{PREFIX}:pages:detail:{page_id}"


def navigation_key(menu_key):
    return f"{PREFIX}:navigation:{menu_key}"


def section_types_key():
    return f"{PREFIX}:section-types"


def page_group(page_id):
    return f"page:{page_id}"


def navigation_group(menu_key):
    return f"navigation:{menu_key}"


# --- low-level registry-based get/set/invalidate ----------------------

def _registry_key(group):
    return f"{PREFIX}:registry:{group}"


def get(key):
    return _cache().get(key)


def set_with_groups(key, value, *, groups):
    """Cache ``value`` under ``key`` and register ``key`` against
    every group in ``groups``, so ``invalidate_groups`` can find and
    drop it later without relying on backend pattern matching."""
    ttl = _ttl()
    cache = _cache()
    cache.set(key, value, ttl)
    for group in groups:
        registry_key = _registry_key(group)
        members = cache.get(registry_key) or set()
        members.add(key)
        cache.set(registry_key, members, ttl)


def invalidate_groups(*groups):
    cache = _cache()
    for group in groups:
        registry_key = _registry_key(group)
        members = cache.get(registry_key) or set()
        if members:
            cache.delete_many(list(members))
        cache.delete(registry_key)


# --- read/write helpers used by the public views ----------------------

def get_pages_list():
    return get(pages_list_key())


def set_pages_list(data):
    set_with_groups(pages_list_key(), data, groups=[PAGES_LIST_GROUP])


def get_sitemap():
    return get(sitemap_key())


def set_sitemap(data):
    set_with_groups(sitemap_key(), data, groups=[SITEMAP_GROUP])


def get_page_detail(page_id):
    return get(page_detail_key(page_id))


def set_page_detail(page_id, data):
    set_with_groups(
        page_detail_key(page_id), data, groups=[page_group(page_id)],
    )


def get_navigation(menu_key):
    return get(navigation_key(menu_key))


def set_navigation(menu_key, data):
    set_with_groups(
        navigation_key(menu_key), data,
        groups=[navigation_group(menu_key)],
    )


def get_section_types():
    return get(section_types_key())


def set_section_types(data):
    # No group: code-derived, nothing ever invalidates it.
    _cache().set(section_types_key(), data, _ttl())


# --- invalidation -------------------------------------------------------

def invalidate_page_detail(*page_ids):
    invalidate_groups(*(page_group(pid) for pid in page_ids))


def invalidate_pages_list():
    invalidate_groups(PAGES_LIST_GROUP)


def invalidate_sitemap():
    invalidate_groups(SITEMAP_GROUP)


def invalidate_navigation(menu_key):
    invalidate_groups(navigation_group(menu_key))


def invalidate_all_navigation():
    from cms_api.models import CmsNavigationMenu

    keys = CmsNavigationMenu.objects.filter(
        is_active=True,
    ).values_list("key", flat=True)
    if keys:
        invalidate_groups(*(navigation_group(key) for key in keys))


def queue_page_ids_invalidation(page_ids):
    """Invalidate the detail cache for every id in ``page_ids`` plus
    the page list, the sitemap and every active navigation menu —
    the full set of public responses a page's own publish state or
    published path can affect. Deferred to ``transaction.on_commit``
    (``robust=True``: a cache error after a successful commit must
    never turn into a 500)."""
    page_ids = list(page_ids)

    def _invalidate():
        if page_ids:
            invalidate_page_detail(*page_ids)
        invalidate_pages_list()
        invalidate_sitemap()
        invalidate_all_navigation()

    transaction.on_commit(_invalidate, robust=True)


def queue_page_change_invalidation(page, *, include_descendants=True):
    """Queue invalidation for ``page`` and, when its own published
    path can have moved its live descendants' paths with it (publish,
    unpublish, rollback, a Wagtail Admin tree move), every live
    descendant too — a public page's rendered path is built from its
    *ancestors'* published slugs (``services/paths.py:
    published_url_path``), not only its own revision."""
    page_ids = [page.pk]
    if include_descendants:
        page_ids += [
            descendant.pk for descendant in page.get_descendants().live()
        ]
    queue_page_ids_invalidation(page_ids)


def queue_navigation_invalidation(menu_key):
    transaction.on_commit(
        lambda: invalidate_navigation(menu_key), robust=True,
    )


def queue_section_change_invalidation(section):
    """Queue invalidation for every ``CmsPage`` whose composition
    references ``section`` (``ReferenceIndex`` reverse lookup — the
    same mechanism ``delete_section``'s dependency guard already
    uses). The page list, sitemap and navigation never embed section
    content, so they are deliberately left alone here.

    ``ReferenceIndex.get_grouped_references_to`` groups by the actual
    *source object* (confirmed by reading ``ReferenceGroups.__iter__``
    — it loads the instance via
    ``content_type.get_object_for_this_type(pk=...)``), and that
    object is an instance of the *base* Wagtail ``Page`` model (multi-
    table inheritance), never the concrete ``CmsPage`` one — confirmed
    empirically, not assumed. ``CmsPage`` is the only concrete page
    model in this project (AD-3), so every ``Page`` instance found
    here is a ``CmsPage`` row.
    """
    referencing_page_ids = sorted({
        source.pk
        for source, _references in (
            ReferenceIndex.get_grouped_references_to(section)
        )
        if isinstance(source, Page)
    })
    if not referencing_page_ids:
        return

    def _invalidate():
        invalidate_page_detail(*referencing_page_ids)

    transaction.on_commit(_invalidate, robust=True)


# --- signal wiring -------------------------------------------------------

def _on_page_signal(sender, instance, **kwargs):
    queue_page_change_invalidation(instance)


def _on_section_signal(sender, instance, **kwargs):
    queue_section_change_invalidation(instance)


def connect_cache_invalidation_receivers():
    from wagtail.signals import (
        page_published,
        page_unpublished,
        post_page_move,
        published,
        unpublished,
    )

    from cms_api.models import CmsPage
    from cms_api.models.cms_section import CmsSection

    page_published.connect(
        _on_page_signal, sender=CmsPage,
        dispatch_uid="cms_api.cache.page_published",
    )
    page_unpublished.connect(
        _on_page_signal, sender=CmsPage,
        dispatch_uid="cms_api.cache.page_unpublished",
    )
    post_page_move.connect(
        _on_page_signal, sender=CmsPage,
        dispatch_uid="cms_api.cache.page_moved",
    )
    published.connect(
        _on_section_signal, sender=CmsSection,
        dispatch_uid="cms_api.cache.section_published",
    )
    unpublished.connect(
        _on_section_signal, sender=CmsSection,
        dispatch_uid="cms_api.cache.section_unpublished",
    )
