# cms_api/services/preview.py
"""Signed, read-only preview tokens (docs/cms-architecture.md §5.7,
AD-15).

A token is issued only to an authenticated user holding the matching
edit permission and is scoped to one object and one specific content
revision. It never carries pickled data: ``signing.dumps``/``loads``
use Django's JSON-backed signer, and ``compress`` is left off, since a
compressed token's leading ``.`` would not survive DRF's default
``[^/.]+`` URL lookup pattern for ``GET /public/preview/{token}/``.

Resolution re-checks the signature, the TTL, that the revision still
belongs to the object it was issued for, and that the *same* user
still holds the edit permission — a token outlives neither the
object, the revision, nor the user's access to it.
"""
from django.contrib.auth import get_user_model
from django.core import signing

from rest_framework.exceptions import NotFound, PermissionDenied

from cms_api.models import CmsPage, CmsSection

PREVIEW_TOKEN_MAX_AGE = 60 * 30  # 30 minutes
PREVIEW_SALT = "cms_api.preview"

KIND_PAGE = "page"
KIND_SECTION = "section"

_MODELS = {KIND_PAGE: CmsPage, KIND_SECTION: CmsSection}
_EDIT_PERMS = {
    KIND_PAGE: "cms_api.change_cmspage",
    KIND_SECTION: "cms_api.change_cmssection",
}


def issue_preview_token(*, kind, obj, user, revision_id=None):
    """Sign a token for ``obj``'s latest (or a named) revision."""
    revision = (
        obj.revisions.filter(id=revision_id).first()
        if revision_id is not None
        else obj.latest_revision
    )
    if revision is None:
        return None, None
    payload = {
        "kind": kind,
        "object_id": obj.pk,
        "revision_id": revision.id,
        "user_id": user.id,
    }
    token = signing.dumps(payload, salt=PREVIEW_SALT, compress=False)
    return token, revision


def resolve_preview_token(*, token):
    """Verify ``token`` and return ``(kind, previewed_object, revision)``.

    ``previewed_object`` is the object reconstructed from the
    revision content (``revision.as_object()``), not the live row.
    """
    try:
        payload = signing.loads(
            token, salt=PREVIEW_SALT, max_age=PREVIEW_TOKEN_MAX_AGE,
        )
    except signing.BadSignature:
        raise NotFound("Invalid or expired preview link.")

    kind = payload.get("kind")
    model = _MODELS.get(kind)
    if model is None:
        raise NotFound("Invalid or expired preview link.")

    user_model = get_user_model()
    user = user_model.objects.filter(
        pk=payload.get("user_id"), is_active=True,
    ).first()
    if user is None or not user.has_perm(_EDIT_PERMS[kind]):
        raise PermissionDenied(
            "You no longer have permission to preview this content."
        )

    obj = model.objects.filter(pk=payload.get("object_id")).first()
    if obj is None:
        raise NotFound("Content not found.")

    revision = obj.revisions.filter(id=payload.get("revision_id")).first()
    if revision is None:
        raise NotFound("Revision not found.")

    return kind, revision.as_object(), revision
