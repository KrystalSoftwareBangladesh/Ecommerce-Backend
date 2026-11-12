# cms_api/services/cms_section.py
"""CmsSection domain operations (docs/cms-architecture.md 6, 8).

Business rules
- A section is created as an unpublished draft (``live=False``);
  create never implies publish, matching the blog_api precedent.
- ``section_type`` is immutable after creation. ``content`` must hold
  exactly one block whose type matches ``section_type`` (also enforced
  on the model).
- Management writes are optimistic-locked: a request carrying
  ``base_revision_id`` that is not the section's latest revision is
  rejected with 409 ``RevisionConflictError``.
- Publish makes the latest revision (or a named revision) live;
  unpublish hides the section without deleting it.
- Archive sets ``archived_at`` and excludes the section from the
  default listing; there is no unarchive in Phase 1 (spec gap).
- Permanent delete is elevated and dependency-guarded: while any
  other object references the section through Wagtail's
  ``ReferenceIndex``, deletion is refused.
- Rollback restores the content of an older revision as a *new*
  revision and publishes it (interpretation R1: rollback = restore +
  publish, gated by ``publish_cms_section``).

Wagtail note: ``DraftStateMixin.publish`` and ``UnpublishAction``
run internal permission checks against the auto-generated Wagtail
codename ``publish_cmssection``/``unpublish_cmssection`` (double
underscore), which are not the spec permissions. Enforcement is done
by DRF ``ModelPermissionAccess`` at the API layer, so the services
call the actions with ``skip_permission_checks=True``.
"""
from django.core.exceptions import (
    ValidationError as DjangoValidationError,
)
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from wagtail.actions.publish_revision import PublishRevisionAction
from wagtail.actions.unpublish import UnpublishAction
from wagtail.log_actions import log
from wagtail.models import ReferenceIndex

from cms_api.models import CmsSection
from cms_api.services.cache import queue_section_change_invalidation


def _validate_schedule(go_live_at, expire_at):
    """``expire_at`` must be in the future and after ``go_live_at``
    (docs/cms-architecture.md 12, AD-13)."""
    errors = {}
    now = timezone.now()
    if expire_at is not None and expire_at <= now:
        errors["expire_at"] = "expire_at must be in the future."
    if (
        go_live_at is not None
        and expire_at is not None
        and expire_at <= go_live_at
    ):
        errors["expire_at"] = "expire_at must be after go_live_at."
    if errors:
        raise ValidationError(errors)


def _clear_stale_expiry(obj, revision, user, log_action):
    """Re-snapshot ``revision`` with ``expire_at`` cleared if it is
    already in the past.

    A revision's ``expire_at`` is frozen in its content JSON when the
    revision is saved. Publishing a revision whose embedded
    ``expire_at`` is already in the past would make the object live
    with a stale expiry already due, so the very next
    ``cms-publish-scheduled`` sweep would unpublish it again
    immediately. Only a plain republish of an existing revision can
    carry a stale value in; a request that sets ``go_live_at``/
    ``expire_at`` explicitly is validated by ``_validate_schedule``
    instead.
    """
    content_obj = revision.as_object()
    if content_obj.expire_at and content_obj.expire_at <= timezone.now():
        obj.expire_at = None
        obj.save(update_fields=["expire_at"])
        return obj.save_revision(user=user, log_action=log_action)
    return revision


class RevisionConflictError(APIException):
    """``base_revision_id`` no longer matches the latest revision."""

    status_code = 409
    default_detail = (
        "The section has been modified since the supplied "
        "base revision."
    )
    default_code = "revision_conflict"


def _full_clean(section):
    """Run model validation, re-raising as a DRF error."""
    try:
        section.full_clean()
    except DjangoValidationError as exc:
        if hasattr(exc, "message_dict"):
            raise ValidationError(exc.message_dict)
        raise ValidationError(exc.messages)


def _get_revision(*, section, revision_id):
    try:
        return section.revisions.get(id=revision_id)
    except section.revisions.model.DoesNotExist:
        raise ValidationError(
            {"revision_id": "Revision not found for this section."}
        )


def _check_base_revision(obj, base_revision_id):
    """Optimistic-lock check shared by section and page writes.

    When ``base_revision_id`` is given it must equal the object's
    ``latest_revision_id`` or a 409 is raised.
    """
    if (
        base_revision_id is not None
        and base_revision_id != obj.latest_revision_id
    ):
        raise RevisionConflictError()


@transaction.atomic
def create_section(*, validated_data, user):
    """Create a new draft ``CmsSection`` and its first revision."""
    section = CmsSection(
        name=validated_data["name"],
        section_type=validated_data["section_type"],
        content=validated_data["content"],
        created_by=user,
        updated_by=user,
        live=False,
    )
    _full_clean(section)
    section.save()
    section.save_revision(user=user, log_action="wagtail.create")
    return section


@transaction.atomic
def update_section(
    *, section, validated_data, user, base_revision_id=None
):
    """Update name/content of an existing section.

    ``section_type`` is immutable. When ``base_revision_id`` is given
    it must equal ``section.latest_revision_id`` or a 409 is raised.
    """
    if (
        "section_type" in validated_data
        and validated_data["section_type"] != section.section_type
    ):
        raise ValidationError(
            {"section_type": "section_type is immutable."}
        )
    if (
        base_revision_id is not None
        and base_revision_id != section.latest_revision_id
    ):
        raise RevisionConflictError()

    if "name" in validated_data:
        section.name = validated_data["name"]
    if "content" in validated_data:
        section.content = validated_data["content"]
    section.updated_by = user
    _full_clean(section)
    section.save()
    section.save_revision(user=user, log_action="wagtail.edit")
    return section


@transaction.atomic
def publish_section(
    *, section, user, revision_id=None, go_live_at=None, expire_at=None,
):
    """Publish the latest (or a named) revision of the section.

    ``go_live_at``/``expire_at`` schedule the section (docs
    §12, AD-13): both are written to the section and snapshotted into
    a new revision, which ``PublishRevisionAction`` either publishes
    immediately or schedules depending on ``go_live_at``. They cannot
    be combined with ``revision_id`` (scheduling always operates on
    the current draft state, not an arbitrary past revision).

    ``PublishRevisionAction`` fires Wagtail's generic ``published``
    signal, which drives referencing-page cache invalidation
    (``services/cache.py``); no explicit call is needed here.
    """
    _validate_schedule(go_live_at, expire_at)
    if go_live_at is not None or expire_at is not None:
        if revision_id is not None:
            raise ValidationError({
                "revision_id": (
                    "Cannot combine revision_id with go_live_at/"
                    "expire_at."
                ),
            })
        if go_live_at is not None:
            section.go_live_at = go_live_at
        if expire_at is not None:
            section.expire_at = expire_at
        _full_clean(section)
        section.save()
        revision = section.save_revision(
            user=user, log_action="wagtail.edit",
        )
    else:
        if not section.live and not section.latest_revision_id:
            raise ValidationError(
                "Section has no revision to publish."
            )
        revision = (
            _get_revision(section=section, revision_id=revision_id)
            if revision_id is not None
            else section.latest_revision
        )
        if revision is None:
            raise ValidationError("Section has no revision to publish.")
        revision = _clear_stale_expiry(
            section, revision, user, "wagtail.edit",
        )
    PublishRevisionAction(
        revision, user=user
    ).execute(skip_permission_checks=True)
    return section


@transaction.atomic
def unpublish_section(*, section, user):
    """Unpublish the section without deleting it."""
    if not section.live:
        raise ValidationError("Section is not live.")
    # Model .unpublish() has no skip parameter and its permission
    # check is Page-only, so call the action directly.
    UnpublishAction(
        section, user=user
    ).execute(skip_permission_checks=True)
    return section


@transaction.atomic
def archive_section(*, section, user):
    """Archive the section (excluded from the default listing).

    Archiving has no Wagtail publish/unpublish signal of its own (it
    only flips our own ``archived_at``), so the referencing-page fan-
    out invalidation (``services/cache.py``) is explicit here.
    """
    if section.archived_at is not None:
        raise ValidationError("Section is already archived.")
    section.archived_at = timezone.now()
    section.updated_by = user
    section.save(update_fields=["archived_at", "updated_by"])
    log(section, "cms_api.archive", user=user)
    queue_section_change_invalidation(section)
    return section


@transaction.atomic
def delete_section(*, section, user):
    """Soft-delete the section unless other objects reference it.

    The dependency guard uses Wagtail's ``ReferenceIndex``: while the
    section is referenced (for example from a page), deletion is
    refused. Sections are never hard-deleted here.
    """
    references = list(
        ReferenceIndex.get_grouped_references_to(section)
    )
    if references:
        raise ValidationError(
            "Cannot delete: the section is referenced by other "
            "content."
        )
    # No cache invalidation call: the guard above just proved nothing
    # references this section, so no page's public output changes.
    section.soft_delete()
    log(section, "wagtail.delete", user=user)
    return section


def list_revisions(*, section):
    """Revisions of the section, newest first."""
    return section.revisions.order_by("-created_at")


@transaction.atomic
def rollback_section(*, section, revision_id, user):
    """Restore an older revision's content and publish it.

    Interpretation R1: rollback creates a new revision holding the
    old content (audit trail stays intact) and publishes it. Gated by
    ``publish_cms_section`` at the API layer.
    """
    old_revision = _get_revision(
        section=section, revision_id=revision_id
    )
    restored = old_revision.as_object()
    section.name = restored.name
    section.content = restored.content
    section.updated_by = user
    _full_clean(section)
    section.save()
    revision = section.save_revision(
        user=user, previous_revision=old_revision
    )
    PublishRevisionAction(
        revision, user=user, previous_revision=old_revision,
        log_action="cms_api.rollback",
    ).execute(skip_permission_checks=True)
    return section
