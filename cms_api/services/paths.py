# cms_api/services/paths.py
"""Published-path resolution (docs/cms-architecture.md §9).

Split out from ``services/pages.py`` so ``services/redirects.py`` can
depend on it without a circular import (``pages.py`` needs the
redirect helpers to create slug-change redirects on publish).
"""


def published_snapshot(page):
    """The page's published content (its live revision), else the
    row itself.

    Shared by the public serializers, the sitemap and redirect
    resolution: a page's own columns may hold unpublished edits
    (``update_page`` writes fields like ``seo_noindex`` straight to
    the row before any publish), so anything that must reflect only
    published state reads through the live revision instead of the
    row.
    """
    revision = page.live_revision
    if revision is not None:
        return revision.as_object()
    return page


def published_slug(page):
    """The page's published slug (live revision), else the row's."""
    revision = page.live_revision
    if revision is not None:
        return revision.as_object().slug or page.slug
    return page.slug


def prospective_url_path(obj):
    """Best-effort draft path for a page-like object that may not be
    live (e.g. a preview revision): slug + the current ancestor
    chain's own slugs, not necessarily the published ones.

    Used only to label a preview response with where the page would
    sit if published now; the public/redirect resolution path always
    goes through ``published_url_path`` instead.
    """
    if obj.pk is None:
        return None
    ancestors = list(obj.get_ancestors())
    slugs = [node.slug for node in ancestors if not node.is_root()]
    slugs.append(obj.slug)
    return "/%s/" % "/".join(slugs)


def published_url_path(page):
    """Public URL built from published state (spec 9).

    Wagtail rewrites ``url_path`` on every save, so a draft slug
    change is visible in ``url_path`` before publish. The public URL
    chain uses each node's live-revision slug, never the draft one.
    """
    nodes = list(page.get_ancestors().select_related("live_revision"))
    nodes.append(page)
    slugs = [
        published_slug(node) for node in nodes if not node.is_root()
    ]
    if not slugs:
        return "/"
    return "/%s/" % "/".join(slugs)
