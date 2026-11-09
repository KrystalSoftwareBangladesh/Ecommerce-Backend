# cms_api/services/pages.py
"""Page lifecycle and composition writes (docs/cms-architecture.md
5.1, 7.1, 7.3, 9).

Pages are Wagtail ``Page`` subclasses: URL hierarchy, revisions and
publish state come from Wagtail; spec permissions are enforced in DRF
and Wagtail actions run with ``skip_permission_checks=True``.

A page is created as a draft. ``template_key`` seeds the initial
composition (AD-3) unless explicit ``sections`` are given. Reserved
paths (``CMS_RESERVED_PATHS``) are rejected on create, slug change
and rollback (the prospective restored URL is validated).
"""
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from rest_framework.exceptions import ValidationError

from wagtail.actions.publish_revision import PublishRevisionAction
from wagtail.actions.unpublish import UnpublishAction
from wagtail.models import Page, ReferenceIndex

from cms_api.models import CmsPage
from cms_api.pages.templates import PAGE_TEMPLATES
from cms_api.services.cms_section import (
    _check_base_revision,
    _full_clean,
    _get_revision,
)
from cms_api.services.composition import (
    apply_section_rows,
)


def _validate_reserved_path(url_path):
    """Reject page paths under a reserved prefix (spec 9)."""
    for reserved in settings.CMS_RESERVED_PATHS:
        if url_path.startswith(reserved):
            raise ValidationError({
                "slug": (
                    "Path '%s' is reserved and cannot be used "
                    "by a CMS page." % url_path
                )
            })


def _prospective_url_path(parent, slug):
    return "%s%s/" % (parent.url_path, slug)


def _validate_url_available(prospective, page):
    """Reject a prospective URL already held by another page."""
    if (
        Page.objects.filter(url_path=prospective)
        .exclude(pk=page.pk)
        .exists()
    ):
        raise ValidationError({
            "slug": (
                "Path '%s' is already in use by another "
                "page." % prospective
            )
        })


def published_slug(page):
    """The page's published slug (live revision), else the row's."""
    revision = page.live_revision
    if revision is not None:
        return revision.as_object().slug or page.slug
    return page.slug


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


def _page_revision(page, revision_id):
    if revision_id is None:
        revision = page.latest_revision
        if revision is None:
            raise ValidationError({
                "detail": "Page has no revision to publish."
            })
        return revision
    return _get_revision(section=page, revision_id=revision_id)


def list_page_revisions(page):
    return page.revisions.order_by("-created_at")


@transaction.atomic
def create_page(*, validated_data, user):
    """Create a draft ``CmsPage`` from a template or given sections."""
    sections_data = validated_data.pop("sections", None)
    template_key = validated_data.pop("template_key", "blank")
    parent = validated_data.pop("parent", None)
    if parent is None:
        parent = Page.objects.get(depth=1)
    slug = validated_data["slug"]
    _validate_reserved_path(_prospective_url_path(parent, slug))
    page = CmsPage(
        live=False,
        owner=user,
        template_key=template_key,
        **validated_data,
    )
    parent.add_child(instance=page)
    _full_clean(page)
    if sections_data is None:
        sections_data = PAGE_TEMPLATES.get(
            template_key, {}
        ).get("sections", [])
    apply_section_rows(page, sections_data)
    page.save_revision(user=user, log_action="cms_api.create")
    return page


@transaction.atomic
def update_page(
    *, page, validated_data, user, base_revision_id=None,
):
    """Update page fields and/or replace the composition.

    ``template_key`` is immutable (the template only seeds the
    initial composition). When ``base_revision_id`` is given it must
    equal ``page.latest_revision_id`` or a 409 is raised.
    """
    _check_base_revision(page, base_revision_id)
    sections_data = validated_data.pop("sections", None)
    if "slug" in validated_data and validated_data["slug"] != page.slug:
        parent = page.get_parent()
        _validate_reserved_path(
            _prospective_url_path(parent, validated_data["slug"])
        )
    for field, value in validated_data.items():
        setattr(page, field, value)
    _full_clean(page)
    if sections_data is not None:
        apply_section_rows(page, sections_data)
    else:
        page.save()
    page.save_revision(user=user, log_action="cms_api.update")
    return page


@transaction.atomic
def delete_page(*, page, user, acknowledge=False):
    """Permanent, dependency-guarded page deletion (spec 5.1).

    The subtree and every Wagtail reference must be acknowledged;
    otherwise a ``ValidationError`` lists each dependency. Navigation
    menu dependencies are checked once ``CmsNavigationMenu`` exists
    (Phase 4).
    """
    dependencies = []
    for child in page.get_children().specific():
        dependencies.append({
            "model": child._meta.label,
            "object_id": child.pk,
            "object": str(child),
        })
    grouped = ReferenceIndex.get_grouped_references_to(page)
    for source, refs in grouped:
        dependencies.append({
            "model": source._meta.label if source else None,
            "object_id": refs[0].object_id,
            "object": str(source) if source else None,
            "fields": sorted({
                ref.describe_source_field() for ref in refs
            }),
        })
    if dependencies and not acknowledge:
        raise ValidationError({
            "detail": (
                "Page is referenced by other content. Repeat "
                "the request with acknowledge=true to delete it "
                "and its subtree."
            ),
            "dependencies": dependencies,
        })
    page.delete()
    return dependencies


@transaction.atomic
def publish_page(*, page, user, revision_id=None):
    revision = _page_revision(page, revision_id)
    PublishRevisionAction(
        revision, user=user,
    ).execute(skip_permission_checks=True)
    return page


@transaction.atomic
def unpublish_page(*, page, user):
    UnpublishAction(page, user=user).execute(
        skip_permission_checks=True
    )
    return page


@transaction.atomic
def archive_page(*, page, user):
    page.archived_at = timezone.now()
    page.save()
    return page


@transaction.atomic
def restore_page(*, page, user):
    page.archived_at = None
    page.save()
    return page


@transaction.atomic
def rollback_page(*, page, revision_id, user):
    """Restore an old revision's fields and composition, publish it.

    Interpretation R1 (as for sections): rollback creates a new
    revision holding the old content and publishes it. Gated by
    ``publish_cms_page`` at the API layer.

    The restored URL is always recalculated from the page's *current*
    parent hierarchy, never taken from the historical revision. An
    ancestor may have had its slug changed since the revision was
    captured; Wagtail's own ``Page.save()`` only recomputes
    ``url_path`` when *this* page's own slug differs from the row
    currently in the database, so a rollback that leaves the slug
    unchanged would otherwise skip recalculation even if the parent
    chain has moved on, leaving a stale prefix. ``get_parent(update=
    True)`` forces a fresh lookup (``get_parent`` caches its result on
    the instance), and descendants are repathed explicitly whenever
    the recalculated path differs, mirroring Wagtail's own slug-change
    cascade (``_update_descendant_url_paths``) for the case Wagtail's
    check does not cover. The "old" path fed to that cascade is read
    straight from the database rather than from ``page.url_path``,
    which may itself be a stale in-memory value on the ``page``
    instance the caller handed in; descendants always carry the
    database's current prefix, never the caller's possibly-stale one.
    """
    old_revision = _page_revision(page, revision_id)
    restored = old_revision.as_object()
    parent = page.get_parent(update=True)
    prospective = _prospective_url_path(parent, restored.slug)
    _validate_reserved_path(prospective)
    _validate_url_available(prospective, page)
    old_url_path = (
        Page.objects.filter(pk=page.pk)
        .values_list("url_path", flat=True)
        .get()
    )
    for field in (
        "title", "slug", "draft_title", "seo_title",
        "template_key", "seo_description", "meta_keywords",
        "og_title", "og_description", "og_image",
        "canonical_url", "seo_noindex", "seo_nofollow",
    ):
        setattr(page, field, getattr(restored, field))
    sections_data = [
        {
            "name": row.name,
            "global_section": row.global_section,
            "content": row.content or None,
            "archived": row.archived_at is not None,
        }
        for row in restored.sections.all()
    ]
    apply_section_rows(page, sections_data)
    _full_clean(page)
    page.set_url_path(parent)
    page.save()
    if page.url_path != old_url_path:
        page._update_descendant_url_paths(old_url_path, page.url_path)
    revision = page.save_revision(
        user=user, previous_revision=old_revision
    )
    PublishRevisionAction(
        revision, user=user, previous_revision=old_revision,
    ).execute(skip_permission_checks=True)
    return page
