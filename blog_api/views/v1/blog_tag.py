# blog_api/views/v1/blog_tag.py
from django_filters.rest_framework import DjangoFilterBackend

from drf_spectacular.utils import extend_schema

from rest_framework import filters, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from EcommerceBackend.core.permission import (
    ModelPermissionAccess,
    PublicReadPermissionMixin,
)

from blog_api.models import BlogTag
from blog_api.serializers import (
    BlogTagCreateSerializer,
    BlogTagDetailSerializer,
    BlogTagListSerializer,
    BlogTagUpdateSerializer,
)
from blog_api.services import delete_blog_tag


@extend_schema(tags=["Blog"])
class BlogTagViewSet(
    PublicReadPermissionMixin,
    viewsets.ModelViewSet,
):
    """
    Blog tags.

    Publicly readable so a storefront can render a tag cloud; managing
    them is driven by Django model permissions.
    """
    permission_classes = [IsAuthenticated, ModelPermissionAccess]
    queryset = BlogTag.objects.filter(deleted_at__isnull=True)
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = [
        'is_active',
    ]
    search_fields = [
        'name',
        'slug',
    ]
    ordering_fields = [
        'name',
        'created_at',
        'id',
    ]
    ordering = ['name', 'id']

    def get_queryset(self):
        queryset = BlogTag.objects.filter(deleted_at__isnull=True)

        if self.action in self.public_actions:
            queryset = queryset.filter(is_active=True)

        return queryset.select_related('created_by', 'updated_by')

    def get_serializer_class(self):
        if self.action == 'list':
            return BlogTagListSerializer

        if self.action == 'create':
            return BlogTagCreateSerializer

        if self.action in ['update', 'partial_update']:
            return BlogTagUpdateSerializer

        return BlogTagDetailSerializer

    def _detail_response(self, tag, response_status):
        return Response(
            BlogTagDetailSerializer(
                tag,
                context=self.get_serializer_context(),
            ).data,
            status=response_status,
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tag = serializer.save()

        return self._detail_response(tag, status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        tag = self.get_object()

        serializer = self.get_serializer(
            tag,
            data=request.data,
            partial=kwargs.pop('partial', False),
        )
        serializer.is_valid(raise_exception=True)
        tag = serializer.save()

        return self._detail_response(tag, status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        tag = self.get_object()

        delete_blog_tag(tag=tag, user=request.user)

        return Response(status=status.HTTP_204_NO_CONTENT)
