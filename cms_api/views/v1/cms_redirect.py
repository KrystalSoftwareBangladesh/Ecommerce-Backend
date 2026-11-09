# cms_api/views/v1/cms_redirect.py
"""Redirect history (management) and resolution (public) (docs/
cms-architecture.md §6, §9).

``Redirect`` belongs to ``wagtail.contrib.redirects``, not ``cms_api``,
so it cannot carry a custom ``cms_api`` codename of its own. Redirects
only ever exist as a byproduct of a CMS page's slug changing, so
management access reuses ``view_cmspage`` rather than the auto
generated ``wagtailredirects.view_redirect`` permission, keeping every
CMS permission a ``cms_api`` codename.
"""
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from wagtail.contrib.redirects.models import Redirect

from cms_api.serializers import (
    CmsRedirectResolveSerializer,
    CmsRedirectSerializer,
)
from cms_api.services import resolve_redirect_path


class CanViewCmsRedirects(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.has_perm("cms_api.view_cmspage")
        )


@extend_schema(tags=["CMS"])
class CmsRedirectViewSet(viewsets.ReadOnlyModelViewSet):
    """``GET /redirects/`` (management) and ``GET /redirects/
    resolve/`` (public, for the Nuxt redirect middleware)."""

    serializer_class = CmsRedirectSerializer
    queryset = Redirect.objects.filter(
        site__isnull=True,
    ).select_related("redirect_page").order_by("-created_at")

    def get_permissions(self):
        if self.action == "resolve":
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated(), CanViewCmsRedirects()]

    @extend_schema(
        responses=CmsRedirectResolveSerializer,
    )
    @action(detail=False, methods=["get"])
    def resolve(self, request):
        path = request.query_params.get("path")
        if not path:
            return Response(
                {"detail": "path is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        resolved = resolve_redirect_path(path)
        if resolved is None:
            return Response(
                {"detail": "Not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"path": resolved})
