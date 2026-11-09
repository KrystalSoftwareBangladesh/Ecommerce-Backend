# cms_api/views/v1/cms_audit_log.py
"""Read-only CMS audit-log API (docs/cms-architecture.md §6, §11).

``view_cmspage`` gates this endpoint, the same reuse (no dedicated
codename) already approved for ``GET /redirects/`` (§16 item 8) —
audit history is a cross-cutting read, not a write on any one model.
"""
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions

from cms_api.serializers.cms_audit_log import (
    CmsAuditLogEntrySerializer,
    CmsAuditLogQuerySerializer,
)
from cms_api.services.audit_log import list_audit_log_entries


class CanViewCmsAuditLog(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.has_perm("cms_api.view_cmspage")
        )


@extend_schema(tags=["CMS"])
class CmsAuditLogView(generics.ListAPIView):
    """``GET /api/v1/cms/audit-logs/`` — merged, descending-timestamp
    activity across every CMS-owned content type.

    Query params: ``start_date``/``end_date`` (ISO 8601; defaults to
    the most recent 90 days, any wider request is clamped to 365
    days), ``action``, ``content_type`` (one of the keys in
    ``CMS_AUDIT_CONTENT_TYPES``).
    """

    permission_classes = [CanViewCmsAuditLog]
    serializer_class = CmsAuditLogEntrySerializer

    def get_queryset(self):
        query = CmsAuditLogQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        return list_audit_log_entries(**query.validated_data)
