# cms_api/services/cache.py
"""Public-response caching for the CMS (docs/cms-architecture.md
§10, AD-12, Phase 5C and its cache-consistency hardening).

Every cached payload lives under a *generation-keyed* key
``cms:<base>:<generation>``, where the generation is an integer
counter kept under ``cms:gen:<base>``:

- ``pages:detail:<id>`` — one page's public detail payload.
- ``pages:list`` — the public page list (``GET /public/pages/``
  with no ``path``).
- ``sitemap`` — the sitemap response.
- ``navigation:<key>`` — one navigation menu's public tree.
- ``section-types`` — the section-type schema; never invalidated
  (derived entirely from code, ``cms_api.sections.registry``), so it
  expires only via its own TTL (e.g. after a deploy changes the
  registry).

Why generations (Phase 5C's literal-key GET/SET/DEL left the
cache-aside race open): a request that read pre-publish content just
before a publishing transaction committed could write it just after
the on-commit invalidation deleted the key — leaving stale content
reachable until the safety-net TTL. Under this scheme that write
lands under the *pre-publish* generation and can never be read
again:

1. A reader captures its family's generation *before* it reads the
   database (``get_*`` returns ``(generation, value)``).
2. It writes only under that captured generation (``set_*`` takes
   the generation back), never under whatever generation is current
   at write time.
3. Invalidation advances the generation (``incr``) from a
   ``transaction.on_commit`` callback — only after a successful
   commit — so every key written under an earlier generation becomes
   unreachable at once, without enumerating payload keys.

A write that lands after an invalidation therefore cannot repopulate
the active namespace: it still carries the old generation while
subsequent readers use the new one. A reader that captures the
generation after the increment is a post-commit reader (the increment
runs on commit) and rebuilds from fresh database content.

Why there is no registry: every payload key is deterministic (base +
generation), so there is nothing to register and nothing for
concurrent workers to clobber — the failure mode of the registry
pattern Phase 5C first copied from ``category_api/services/cache.py``
(a read-modify-write per group that could drop a registration and
strand a payload key past every later invalidation).

Atomicity — the module's only concurrency assumptions: ``add`` is
set-if-absent and ``incr`` is a single counter step, on Redis
(``SETNX`` and a Lua ``EXISTS``+``INCRBY``, django-redis) and on
``LocMemCache`` (a lock around the whole operation). Generation keys
are created with ``timeout=None`` (never expire) and only advanced
with ``incr``, so TTL expiry cannot reset a counter. Seeding is
``time.time_ns()``, not 0: a generation key dropped by an evicting
backend (``LocMemCache`` culls past ``MAX_ENTRIES`` at random; a
Redis under memory pressure can evict any key) and re-created must
never resurrect an older era's payload keys, and a fresh seed is
always above every value the previous era reached. Residual: two
re-seeds inside one wall-clock tick, or a clock step backwards across
a drop, could in principle revive an old key;
``CMS_PUBLIC_CACHE_TTL`` bounds any such window.

Honest limits of that design:
- Cross-process invalidation holds wherever the ``"cms"`` cache is
  shared across processes — Redis in production (one keyspace; any
  worker's increment hits the same counter). ``LocMemCache`` is
  per-process (Django's backend keeps a named store per process): it
  never shared a cache across processes, so there is nothing to
  invalidate across them — a backend property, not a module one.
- Generation keys never expire: one tiny persistent counter per
  payload family (per page id, per menu key) — bounded by the number
  of CMS pages and menus ever read.
- ``invalidate_all_page_details`` costs one increment per page id
  (the ids already come from the database).

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

Global section fan-out: a section change advances the generation of
*every* cached page detail (``invalidate_all_page_details``), not
only the pages found via ``ReferenceIndex``. The index tracks a
page's *current* (possibly draft) composition rows, while the public
payload is built from the page's *published* revision — so a page
whose unpublished draft dropped section S is invisible to the index
while its published output still embeds S's published content.
Enumerating dependencies from published revision content was the
alternative; advancing every page's generation is the simpler
reliable option. The cost is bounded and one-sided: a section change
recomputes page payloads on the next read (one query + one increment
per page), never a stale miss. The page list, sitemap and navigation
never embed section content (verified against
``CmsPagePublicListSerializer``/``CmsPagePublicDetailSerializer``
and ``resolve_navigation_tree``: only the detail payload resolves
sections), so they are deliberately left out of that fan-out.
"""
import time

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

def _generation_key(base):
    return f"{PREFIX}:gen:{base}"


def _payload_key(base, generation):
    return f"{PREFIX}:{base}:{generation}"


def _pages_list_base():
    return "pages:list"


def _sitemap_base():
    return "sitemap"


def _page_detail_base(page_id):
    return f"pages:detail:{page_id}"


def _navigation_base(menu_key):
    return f"navigation:{menu_key}"


def _section_types_base():
    return "section-types"


# --- generations --------------------------------------------------------

def _seed():
    # New-era generation values start at the wall clock in
    # nanoseconds, never at 0: a generation key dropped by an
    # evicting backend must not resurrect payload keys of an older
    # era, and any fresh seed is above every value a previous era
    # reached (see module docstring).
    return time.time_ns()


def _current_generation(base):
    cache = _cache()
    gen_key = _generation_key(base)
    generation = cache.get(gen_key)
    if generation is None:
        cache.add(gen_key, _seed(), timeout=None)
        generation = cache.get(gen_key)
        if generation is None:
            # DummyCache stores nothing — its set/add are no-ops
            # too, so this value is never observed again.
            generation = _seed()
    return generation


def _bump(base):
    """Advance ``base``'s generation, making every payload written
    under an earlier generation unreachable. Called only from
    ``transaction.on_commit`` callbacks (or by tests): generations
    move after successful database commits, never before."""
    cache = _cache()
    gen_key = _generation_key(base)
    try:
        cache.incr(gen_key)
    except ValueError:
        # Key absent: DummyCache stores nothing (every incr reports
        # a missing key and there is no cached payload to orphan),
        # or a backend dropped it. A fresh seed still keeps every
        # older payload key unreachable; add() is set-if-absent, so
        # it can never lower a concurrent bump's value.
        cache.add(gen_key, _seed(), timeout=None)


# --- read/write helpers used by the public views ------------------------
#
# Contract: ``get_*`` captures the current generation *before* the
# caller reads the database and returns ``(generation, value)``;
# ``set_*`` must be handed that same generation so the payload is
# written under the key the read was made under — never under the
# generation current at write time (that would reopen the cache-aside
# race; see module docstring).

def _read(base):
    generation = _current_generation(base)
    return generation, _cache().get(_payload_key(base, generation))


def _write(base, generation, value):
    _cache().set(_payload_key(base, generation), value, _ttl())


def get_pages_list():
    return _read(_pages_list_base())


def set_pages_list(generation, data):
    _write(_pages_list_base(), generation, data)


def get_sitemap():
    return _read(_sitemap_base())


def set_sitemap(generation, data):
    _write(_sitemap_base(), generation, data)


def get_page_detail(page_id):
    return _read(_page_detail_base(page_id))


def set_page_detail(generation, page_id, data):
    _write(_page_detail_base(page_id), generation, data)


def get_navigation(menu_key):
    return _read(_navigation_base(menu_key))


def set_navigation(generation, menu_key, data):
    _write(_navigation_base(menu_key), generation, data)


def get_section_types():
    return _read(_section_types_base())


def set_section_types(generation, data):
    # Generation is never advanced: code-derived (module docstring).
    _write(_section_types_base(), generation, data)


# --- invalidation -------------------------------------------------------

def invalidate_page_detail(*page_ids):
    for page_id in page_ids:
        _bump(_page_detail_base(page_id))


def invalidate_all_page_details():
    """Advance the generation of every cached page detail — the
    fan-out used for any global section change (module docstring).
    Page ids come from the database (the same pattern
    ``invalidate_all_navigation`` uses) because a registry of cached
    keys is exactly the shared mutable state this module must not
    keep."""
    from cms_api.models import CmsPage

    invalidate_page_detail(*CmsPage.objects.values_list("pk", flat=True))


def invalidate_pages_list():
    _bump(_pages_list_base())


def invalidate_sitemap():
    _bump(_sitemap_base())


def invalidate_navigation(menu_key):
    _bump(_navigation_base(menu_key))


def invalidate_all_navigation():
    from cms_api.models import CmsNavigationMenu

    keys = CmsNavigationMenu.objects.filter(
        is_active=True,
    ).values_list("key", flat=True)
    for key in keys:
        invalidate_navigation(key)


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
    ``section``: every page detail's generation is advanced instead.
    The page list, sitemap and navigation never embed section
    content, so they are deliberately left alone here.
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
