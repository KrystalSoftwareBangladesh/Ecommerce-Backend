from django.utils import timezone
from drf_spectacular.utils import extend_schema

from rest_framework import viewsets, filters, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from EcommerceBackend.core.permission import PublicReadPermissionMixin

from origin_api.models import Origin
from origin_api.serializers import (
    OriginListSerializer,
    OriginDetailSerializer,
    OriginCreateSerializer,
    OriginUpdateSerializer,
)


@extend_schema(tags=["Origins"])
class OriginViewSet(PublicReadPermissionMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = [
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at', 'id']
    ordering = ['name', 'id']

    def get_queryset(self):
        return Origin.objects.filter(
            is_active=True
        ).select_related('parent', 'created_by', 'updated_by')

    def get_serializer_class(self):
        if self.action == 'list':
            return OriginListSerializer
        if self.action == 'retrieve':
            return OriginDetailSerializer
        if self.action == "create":
            return OriginCreateSerializer
        if self.action in ["update", "partial_update"]:
            return OriginUpdateSerializer

    def perform_create(self, serializer):
        serializer.save(
            created_by=self.request.user,
            updated_by=self.request.user
        )

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.updated_by = request.user
        instance.is_active = False
        instance.deleted_at = timezone.now()
        instance.save()
        return Response(status=status.HTTP_204_NO_CONTENT)
