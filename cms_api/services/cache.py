# cms_api/services/cache.py
"""Public-response caching for the CMS (docs/cms-architecture.md
§10, AD-12, Phase 5C).

Every cached payload lives under exactly one literal key and is
read, written and deleted under that key alone — no key registry and
no ``delete_pattern()`` (unavailable on ``LocMemCache``/
``DummyCache``, and explicitly excluded by this phase's brief):

- ``cms:pages:detail:<id>`` — one page's public detail payload.
- ``cms:pages:list`` — the public page list (``GET /public/pages/``
  with no ``path``).
- ``cms:sitemap`` — the sitemap response.
- ``cms:navigation:<key>`` — one navigation menu's public tree.
- ``cms:section-types`` — the section-type schema; never invalidated
  (derived entirely from code, ``cms_api.sections.registry``), so it
  expires only via its own TTL (e.g. after a deploy changes the
  registry).

Why there is no registry (Phase 5C first mirrored the
``category_api`` registry pattern): every invalidation group here is
exactly one deterministic key, so the registry's read-modify-write
was pure overhead *and* a real race — two workers could interleave
get/add/set on one registry entry and drop a registration, and a
write landing between an invalidation's member deletes and its
registry delete orphaned the payload key, invisible to every later
invalidation. Single-key GET/SET/DEL are atomic on Redis and on
``LocMemCache`` (a lock per operation), so literal-key operations
let no worker clobber another's state, and invalidation cannot
strand a key.

Honest limits of that design:
- Cross-process invalidation holds wherever the ``"cms"`` cache is
  shared across processes — Redis in production (one keyspace; any
  worker's DEL hits the same keys). ``LocMemCache`` is per-process
  (Django's backend keeps a named store per process): it never
  shared a cache across processes, so there is nothing to
  invalidate across them — a backend property, not a module one.
- The cache-aside race remains: a reader that loaded pre-change
  content just before a commit can write it just after the
  on-commit invalidation ran. That window is bounded by
  ``CMS_PUBLIC_CACHE_TTL`` (the 5-minute safety net), not zero.

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

Global section fan-out: a section change drops *every* cached page
detail (``invalidate_all_page_details``), not only the pages found
via ``ReferenceIndex``. The index tracks a page's *current*
(possibly draft) composition rows, while the public payload is built
from the page's *published* revision — so a page whose unpublished
draft dropped section S is invisible to the index while its
published output still embeds S's published content. Enumerating
dependencies from published revision content was the alternative;
dropping every page detail is the simpler reliable option. The cost
is bounded and one-sided: a section change recomputes page payloads
on the next read (one query + one ``delete_many``), never a stale
miss.
"""
from django.conf import settings
from django.core.cache import caches
from django.db import transaction

CACHE_ALIAS = "cms"
PREFIX = "cms"


def _cache():
    # Resolved fresh on every call (never bound to a module-level
    # name) so tests can swap the "cms" alias with
    # ``override_settings`` and have it take effect immediately.
    return caches[CACHE_ALIAS]


def _ttl():
    return settings.CMS_PUBLIC_CACHE_TTL


# --- keys ---------------------------------------------------------------

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


# --- low-level get/set/delete -------------------------------------------

def get(key):
    return _cache().get(key)


def _set(key, value):
    _cache().set(key, value, _ttl())


def _delete(*keys):
    keys = [key for key in keys if key]
    if keys:
        _cache().delete_many(keys)


# --- read/write helpers used by the public views ------------------------

def get_pages_list():
    return get(pages_list_key())


def set_pages_list(data):
    _set(pages_list_key(), data)


def get_sitemap():
    return get(sitemap_key())


def set_sitemap(data):
    _set(sitemap_key(), data)


def get_page_detail(page_id):
    return get(page_detail_key(page_id))


def set_page_detail(page_id, data):
    _set(page_detail_key(page_id), data)


def get_navigation(menu_key):
    return get(navigation_key(menu_key))


def set_navigation(menu_key, data):
    _set(navigation_key(menu_key), data)


def get_section_types():
    return get(section_types_key())


def set_section_types(data):
    # Never invalidated: code-derived (see module docstring).
    _set(section_types_key(), data)


# --- invalidation -------------------------------------------------------

def invalidate_page_detail(*page_ids):
    _delete(*(page_detail_key(pid) for pid in page_ids))


def invalidate_all_page_details():
    """Drop every cached page detail — the fan-out used for any
    global section change (see module docstring). Page ids come from
    the database (the same pattern ``invalidate_all_navigation``
    uses) because a registry of cached keys is exactly the shared
    mutable state this module must not keep."""
    from cms_api.models import CmsPage

    invalidate_page_detail(*CmsPage.objects.values_list("pk", flat=True))


def invalidate_pages_list():
    _delete(pages_list_key())


def invalidate_sitemap():
    _delete(sitemap_key())


def invalidate_navigation(menu_key):
    _delete(navigation_key(menu_key))


def invalidate_all_navigation():
    from cms_api.models import CmsNavigationMenu

    keys = CmsNavigationMenu.objects.filter(
        is_active=True,
    ).values_list("key", flat=True)
    _delete(*(navigation_key(key) for key in keys))


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
    """Queue invalidation for every cached page detail.

    A global section's published content is embedded in each
    published page that references it, and the public payload comes
    from the page's *published* revision — but the only cheap reverse
    lookup (``ReferenceIndex``) tracks each page's *current*
    (possibly draft) composition. A page whose unpublished draft
    dropped ``section`` is therefore invisible to the index while its
    published output still embeds it, so the fan-out never narrows on
    ``section``: every page detail is dropped instead. The page list,
    sitemap and navigation never embed section content, so they are
    deliberately left alone here.
    """
    transaction.on_commit(invalidate_all_page_details, robust=True)


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
