# cms_api/views/v1/cms_section.py
"""CMS section API (docs/cms-architecture.md 6, 8).

All endpoints are authenticated and backed by Django model
permissions: standard CRUD uses ``add/change/view/delete_cmssection``,
the lifecycle actions use the custom CMS permissions declared in
``custom_permissions``.
"""
from drf_spectacular.utils import extend_schema

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from wagtail.models import ReferenceIndex

from EcommerceBackend.core.permission import ModelPermissionAccess

from cms_api.models import CmsSection
from cms_api.sections import section_type_schemas
from cms_api.serializers import (
    CmsSectionCreateSerializer,
    CmsSectionDetailSerializer,
    CmsSectionListSerializer,
    CmsSectionPreviewTokenResponseSerializer,
    CmsSectionPreviewTokenSerializer,
    CmsSectionPublishSerializer,
    CmsSectionReferenceSerializer,
    CmsSectionRevisionSerializer,
    CmsSectionRollbackSerializer,
    CmsSectionUpdateSerializer,
    SectionTypeSchemaSerializer,
)
from cms_api.services import (
    archive_section,
    delete_section,
    issue_preview_token,
    list_revisions,
    publish_section,
    rollback_section,
    unpublish_section,
)
from cms_api.services import cache as cms_cache
from cms_api.services.preview import KIND_SECTION, PREVIEW_TOKEN_MAX_AGE


@extend_schema(tags=["CMS"])
class CmsSectionViewSet(viewsets.ModelViewSet):
    """CRUD plus publish, unpublish, archive, revisions and
    rollback for CMS sections.

    Listing excludes archived sections unless ``?archived=true`` is
    given. ``destroy`` refuses to delete a section that is referenced
    by other content.
    """

    permission_classes = [IsAuthenticated, ModelPermissionAccess]
    custom_permissions = {
        "publish": "publish_cms_section",
        "unpublish": "unpublish_cms_section",
        "archive": "archive_cms_section",
        "rollback": "publish_cms_section",
        "revisions": "view_cmssection",
        "references": "view_cmssection",
        "preview_token": "change_cmssection",
    }
    queryset = CmsSection.objects.filter(is_active=True)

    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            "created_by",
            "updated_by",
        )
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
            return CmsSectionListSerializer
        if self.action == "create":
            return CmsSectionCreateSerializer
        if self.action in ("update", "partial_update"):
            return CmsSectionUpdateSerializer
        return CmsSectionDetailSerializer

    def _detail_response(
        self,
        response_status=status.HTTP_200_OK,
        instance=None,
    ):
        if instance is None:
            instance = self.get_object()
        return Response(
            CmsSectionDetailSerializer(instance).data,
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
        section = self.get_object()
        delete_section(section=section, user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        request=CmsSectionPublishSerializer,
        responses=CmsSectionDetailSerializer,
    )
    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        section = self.get_object()
        serializer = CmsSectionPublishSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        publish_section(
            section=section,
            user=request.user,
            revision_id=serializer.validated_data.get(
                "revision_id"
            ),
            go_live_at=serializer.validated_data.get("go_live_at"),
            expire_at=serializer.validated_data.get("expire_at"),
        )
        return self._detail_response()

    @extend_schema(responses=CmsSectionDetailSerializer)
    @action(detail=True, methods=["post"])
    def unpublish(self, request, pk=None):
        section = self.get_object()
        unpublish_section(section=section, user=request.user)
        return self._detail_response()

    @extend_schema(responses=CmsSectionDetailSerializer)
    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        section = self.get_object()
        archive_section(section=section, user=request.user)
        return self._detail_response()

    @extend_schema(
        responses=CmsSectionRevisionSerializer(many=True)
    )
    @action(detail=True, methods=["get"])
    def revisions(self, request, pk=None):
        section = self.get_object()
        return Response(
            CmsSectionRevisionSerializer(
                list_revisions(section=section),
                many=True,
            ).data
        )

    @extend_schema(
        request=CmsSectionRollbackSerializer,
        responses=CmsSectionDetailSerializer,
    )
    @action(detail=True, methods=["post"])
    def rollback(self, request, pk=None):
        section = self.get_object()
        serializer = CmsSectionRollbackSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)
        rollback_section(
            section=section,
            revision_id=serializer.validated_data[
                "revision_id"
            ],
            user=request.user,
        )
        return self._detail_response()

    @extend_schema(
        responses=CmsSectionReferenceSerializer(many=True)
    )
    @action(detail=True, methods=["get"])
    def references(self, request, pk=None):
        section = self.get_object()
        items = []
        grouped = ReferenceIndex.get_grouped_references_to(
            section
        )
        for source, refs in grouped:
            items.append({
                "model": (
                    source._meta.label if source else None
                ),
                "object_id": refs[0].object_id,
                "object": str(source) if source else None,
                "fields": sorted({
                    ref.describe_source_field() for ref in refs
                }),
            })
        return Response(items)

    @extend_schema(
        request=CmsSectionPreviewTokenSerializer,
        responses=CmsSectionPreviewTokenResponseSerializer,
    )
    @action(
        detail=True, methods=["post"], url_path="preview-token",
    )
    def preview_token(self, request, pk=None):
        section = self.get_object()
        serializer = CmsSectionPreviewTokenSerializer(
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)
        token, revision = issue_preview_token(
            kind=KIND_SECTION,
            obj=section,
            user=request.user,
            revision_id=serializer.validated_data.get("revision_id"),
        )
        if token is None:
            return Response(
                {"detail": "Section has no revision to preview."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({
            "token": token,
            "revision_id": revision.id,
            "expires_in": PREVIEW_TOKEN_MAX_AGE,
        })


@extend_schema(tags=["CMS"])
class SectionTypeViewSet(viewsets.ViewSet):
    """Registered CMS section types and their schemas.

    The schema is derived entirely from code
    (``cms_api.sections.registry``), the same for every caller, so one
    cached response is shared across all authenticated users — it is
    read only after DRF's own permission check has already run.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses=SectionTypeSchemaSerializer(many=True)
    )
    def list(self, request):
        cached = cms_cache.get_section_types()
        if cached is not None:
            return Response(cached)
        data = section_type_schemas()
        cms_cache.set_section_types(data)
        return Response(data)
