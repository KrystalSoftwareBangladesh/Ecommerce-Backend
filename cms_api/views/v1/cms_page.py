# cms_api/views/v1/cms_page.py
"""CMS page management and public read APIs (spec 6).

Management endpoints follow the ``CmsSectionViewSet`` pattern:
spec permissions are enforced here (``publish_cms_page``,
``unpublish_cms_page``, ``archive_cms_page``) and Wagtail actions run
with ``skip_permission_checks=True`` in the services. The composition
row route serves GET/PATCH/DELETE, so its permissions are keyed by
HTTP method.

The public viewset exposes published content only (draft isolation):
unpublished and archived pages 404, and global sections resolve to
their published content.
"""
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from EcommerceBackend.core.permission import ModelPermissionAccess

from cms_api.models import CmsPage
from cms_api.serializers.cms_page import (
    CmsPageCreateSerializer,
    CmsPageDetailSerializer,
    CmsPageListSerializer,
    CmsPagePublishSerializer,
    CmsPagePublicDetailSerializer,
    CmsPagePublicListSerializer,
    CmsPageRevisionSerializer,
    CmsPageRollbackSerializer,
    CmsPageSectionCreateSerializer,
    CmsPageSectionReorderSerializer,
    CmsPageSectionSerializer,
    CmsPageSectionUpdateSerializer,
    CmsPageUpdateSerializer,
)
from cms_api.services import (
    archive_page,
    delete_page,
    duplicate_page_section,
    get_page_section,
    list_page_revisions,
    publish_page,
    published_url_path,
    remove_page_section,
    reorder_page_sections,
    restore_page,
    rollback_page,
    unpublish_page,
)


def _base_revision_id(request):
    """Optional ``base_revision_id`` query param (row deletes)."""
    raw = request.query_params.get("base_revision_id")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


@extend_schema(tags=["CMS Pages"])
class CmsPageViewSet(viewsets.ModelViewSet):
    """Page CRUD, lifecycle, revisions and composition writes."""

    permission_classes = [IsAuthenticated, ModelPermissionAccess]
    custom_permissions = {
        "publish": "publish_cms_page",
        "unpublish": "unpublish_cms_page",
        "archive": "archive_cms_page",
        "restore": "archive_cms_page",
        "rollback": "publish_cms_page",
        "revisions": "view_cmspage",
        "add_section": "change_cmspage",
        "section_row": {
            "GET": "view_cmspage",
            "PATCH": "change_cmspage",
            "DELETE": "change_cmspage",
        },
        "duplicate_section": "change_cmspage",
        "reorder_sections": "change_cmspage",
    }
    queryset = CmsPage.objects.all()

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action == "list":
            if self.request.query_params.get("archived") == "true":
                queryset = queryset.filter(
                    archived_at__isnull=False
                )
            else:
                queryset = queryset.filter(
                    archived_at__isnull=True
                )
        return queryset

    def get_serializer_class(self):
        if self.action == "list":
            return CmsPageListSerializer
        if self.action == "create":
            return CmsPageCreateSerializer
        if self.action in ("update", "partial_update"):
            return CmsPageUpdateSerializer
        return CmsPageDetailSerializer

    def _detail_response(
        self,
        response_status=status.HTTP_200_OK,
        instance=None,
    ):
        if instance is None:
            instance = self.get_object()
        return Response(
            CmsPageDetailSerializer(instance).data,
            status=response_status,
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return self._detail_response(
            status.HTTP_201_CREATED,
            instance=serializer.instance,
        )

    def update(self, request, *args, **kwargs):
        super().update(request, *args, **kwargs)
        return self._detail_response()

    def destroy(self, request, *args, **kwargs):
        page = self.get_object()
        acknowledge = (
            request.query_params.get("acknowledge") == "true"
        )
        delete_page(
            page=page,
            user=request.user,
            acknowledge=acknowledge,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        request=CmsPagePublishSerializer,
        responses=CmsPageDetailSerializer,
    )
    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        serializer = CmsPagePublishSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        publish_page(
            page=self.get_object(),
            user=request.user,
            revision_id=serializer.validated_data.get(
                "revision_id"
            ),
        )
        return self._detail_response()

    @extend_schema(responses=CmsPageDetailSerializer)
    @action(detail=True, methods=["post"])
    def unpublish(self, request, pk=None):
        unpublish_page(page=self.get_object(), user=request.user)
        return self._detail_response()

    @extend_schema(responses=CmsPageDetailSerializer)
    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        archive_page(page=self.get_object(), user=request.user)
        return self._detail_response()

    @extend_schema(responses=CmsPageDetailSerializer)
    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        restore_page(page=self.get_object(), user=request.user)
        return self._detail_response()

    @extend_schema(responses=CmsPageRevisionSerializer(many=True))
    @action(detail=True, methods=["get"])
    def revisions(self, request, pk=None):
        page = self.get_object()
        return Response(
            CmsPageRevisionSerializer(
                list_page_revisions(page), many=True,
            ).data
        )

    @extend_schema(
        request=CmsPageRollbackSerializer,
        responses=CmsPageDetailSerializer,
    )
    @action(detail=True, methods=["post"])
    def rollback(self, request, pk=None):
        serializer = CmsPageRollbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rollback_page(
            page=self.get_object(),
            revision_id=serializer.validated_data["revision_id"],
            user=request.user,
        )
        return self._detail_response()

    @extend_schema(
        request=CmsPageSectionCreateSerializer,
        responses=CmsPageSectionSerializer,
    )
    @action(detail=True, methods=["post"], url_path="sections")
    def add_section(self, request, pk=None):
        page = self.get_object()
        serializer = CmsPageSectionCreateSerializer(
            data=request.data,
            context={"request": request, "page": page},
        )
        serializer.is_valid(raise_exception=True)
        row = serializer.save()
        return Response(
            CmsPageSectionSerializer(row).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        request=CmsPageSectionUpdateSerializer,
        responses=CmsPageSectionSerializer,
    )
    @action(
        detail=True,
        methods=["get", "patch", "delete"],
        url_path=r"sections/(?P<section_id>[0-9]+)",
    )
    def section_row(self, request, pk=None, section_id=None):
        page = self.get_object()
        section = get_page_section(page, section_id)
        if request.method == "DELETE":
            remove_page_section(
                page=page,
                section=section,
                user=request.user,
                base_revision_id=_base_revision_id(request),
            )
            return Response(status=status.HTTP_204_NO_CONTENT)
        if request.method == "PATCH":
            serializer = CmsPageSectionUpdateSerializer(
                section,
                data=request.data,
                partial=True,
                context={"request": request, "page": page},
            )
            serializer.is_valid(raise_exception=True)
            section = serializer.save()
        return Response(CmsPageSectionSerializer(section).data)

    @extend_schema(responses=CmsPageSectionSerializer)
    @action(
        detail=True,
        methods=["post"],
        url_path=r"sections/(?P<section_id>[0-9]+)/duplicate",
    )
    def duplicate_section(self, request, pk=None, section_id=None):
        page = self.get_object()
        section = get_page_section(page, section_id)
        row = duplicate_page_section(
            page=page,
            section=section,
            user=request.user,
            base_revision_id=_base_revision_id(request),
        )
        return Response(
            CmsPageSectionSerializer(row).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        request=CmsPageSectionReorderSerializer,
        responses=CmsPageSectionSerializer(many=True),
    )
    @action(
        detail=True, methods=["put"], url_path="sections/reorder",
    )
    def reorder_sections(self, request, pk=None):
        page = self.get_object()
        serializer = CmsPageSectionReorderSerializer(
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)
        reorder_page_sections(
            page=page,
            order=serializer.validated_data["order"],
            user=request.user,
            base_revision_id=serializer.validated_data.get(
                "base_revision_id"
            ),
        )
        return Response(
            CmsPageSectionSerializer(
                page.sections.all(), many=True,
            ).data
        )


@extend_schema(tags=["CMS Pages"])
class CmsPagePublicViewSet(viewsets.GenericViewSet):
    """Published pages for the storefront (spec 6).

    ``GET /cms/public/pages/`` returns the published list;
    ``GET /cms/public/pages/?path=/about-us/`` returns the published
    page with its resolved composition. Unpublished or archived
    pages return 404.
    """

    permission_classes = [AllowAny]
    queryset = CmsPage.objects.filter(
        live=True, archived_at__isnull=True,
    ).select_related("live_revision").prefetch_related(
        "sections__global_section",
    )

    @extend_schema(
        parameters=[],
        responses={
            200: CmsPagePublicDetailSerializer,
            404: None,
        },
    )
    def list(self, request):
        path = request.query_params.get("path")
        if path is not None:
            page = next(
                (
                    row for row in self.get_queryset()
                    if published_url_path(row) == path
                ),
                None,
            )
            if page is None:
                return Response(
                    {"detail": "Not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            return Response(
                CmsPagePublicDetailSerializer(page).data
            )
        pages = self.get_queryset().order_by("url_path")
        return Response(
            CmsPagePublicListSerializer(pages, many=True).data
        )
