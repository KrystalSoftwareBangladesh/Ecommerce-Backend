# cms_api/views/v1/cms_media.py
"""CMS media management APIs (docs/cms-architecture.md 5.6, 6, 8, 11).

``manage_cms_media`` is the single permission for every action here
(config, images, documents alike), the same one-permission-for-
everything shape ``CmsNavigationPermission`` uses for navigation —
there is no public read for media (§6 lists it as management-only).
"""
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from wagtail.documents.models import Document
from wagtail.images.models import Image

from cms_api.models import CmsMediaConfig
from cms_api.serializers.cms_media import (
    CmsDocumentCreateSerializer,
    CmsDocumentDetailSerializer,
    CmsDocumentListSerializer,
    CmsDocumentUpdateSerializer,
    CmsImageCreateSerializer,
    CmsImageDetailSerializer,
    CmsImageListSerializer,
    CmsImageUpdateSerializer,
    CmsMediaConfigSerializer,
)
from cms_api.services import delete_document, delete_image


class CmsMediaPermission(permissions.BasePermission):
    """``cms.media.manage`` (§8): one permission for every media
    operation."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.has_perm("cms_api.manage_cms_media")
        )


@extend_schema(tags=["CMS Media"])
class CmsMediaConfigView(APIView):
    """``GET/PATCH /api/v1/cms/media-config/`` — the singleton media
    configuration (created with its defaults on first access)."""

    permission_classes = [CmsMediaPermission]

    @extend_schema(responses=CmsMediaConfigSerializer)
    def get(self, request):
        return Response(
            CmsMediaConfigSerializer(CmsMediaConfig.get_solo()).data
        )

    @extend_schema(
        request=CmsMediaConfigSerializer,
        responses=CmsMediaConfigSerializer,
    )
    def patch(self, request):
        config = CmsMediaConfig.get_solo()
        serializer = CmsMediaConfigSerializer(
            config,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(CmsMediaConfigSerializer(config).data)


@extend_schema(tags=["CMS Media"])
class CmsImageViewSet(viewsets.ModelViewSet):
    """Images (``wagtailimages.Image``) CRUD. ``DELETE`` is refused
    (400, structured dependency list) while the image is referenced
    from any CMS content — no ``acknowledge`` override, matching
    ``delete_section``."""

    permission_classes = [CmsMediaPermission]
    queryset = Image.objects.all().order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "list":
            return CmsImageListSerializer
        if self.action == "create":
            return CmsImageCreateSerializer
        if self.action in ("update", "partial_update"):
            return CmsImageUpdateSerializer
        return CmsImageDetailSerializer

    def _detail_response(
        self, response_status=status.HTTP_200_OK, instance=None,
    ):
        if instance is None:
            instance = self.get_object()
        return Response(
            CmsImageDetailSerializer(
                instance, context=self.get_serializer_context(),
            ).data,
            status=response_status,
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return self._detail_response(
            status.HTTP_201_CREATED, instance=serializer.instance,
        )

    def update(self, request, *args, **kwargs):
        super().update(request, *args, **kwargs)
        return self._detail_response()

    def destroy(self, request, *args, **kwargs):
        image = self.get_object()
        delete_image(image=image, user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["CMS Media"])
class CmsDocumentViewSet(viewsets.ModelViewSet):
    """Documents (``wagtaildocs.Document``) CRUD. Same delete-guard
    behaviour as images."""

    permission_classes = [CmsMediaPermission]
    queryset = Document.objects.all().order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "list":
            return CmsDocumentListSerializer
        if self.action == "create":
            return CmsDocumentCreateSerializer
        if self.action in ("update", "partial_update"):
            return CmsDocumentUpdateSerializer
        return CmsDocumentDetailSerializer

    def _detail_response(
        self, response_status=status.HTTP_200_OK, instance=None,
    ):
        if instance is None:
            instance = self.get_object()
        return Response(
            CmsDocumentDetailSerializer(
                instance, context=self.get_serializer_context(),
            ).data,
            status=response_status,
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return self._detail_response(
            status.HTTP_201_CREATED, instance=serializer.instance,
        )

    def update(self, request, *args, **kwargs):
        super().update(request, *args, **kwargs)
        return self._detail_response()

    def destroy(self, request, *args, **kwargs):
        document = self.get_object()
        delete_document(document=document, user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
