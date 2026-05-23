# product_api/views/v1/brand.py
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.filters import SearchFilter, OrderingFilter

from EcommerceBackend.core.permission import PublicListPermissionMixin

from product_api.models import Brand
from product_api.serializers import (
    BrandListSerializer,
    BrandDetailSerializer,
    BrandCreateUpdateSerializer,
)


@extend_schema(tags=["Brands"])
class BrandViewSet(PublicListPermissionMixin, viewsets.ModelViewSet):
    """
    ViewSet for Brand CRUD operations.

    Features:
    - Public list endpoint (no authentication required)
    - Authenticated create, update, delete
    - Search by name and description
    - Filter by active status
    - Ordering by name, created_at
    """
    queryset = Brand.objects.filter(is_active=True, deleted_at__isnull=True)
    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]
    filterset_fields = [
        'is_active',
    ]
    search_fields = [
        'name',
        'description',
    ]
    ordering_fields = [
        'name',
        'created_at',
        'id',
    ]
    ordering = ['name', 'id']

    def get_serializer_class(self):
        """
        Return appropriate serializer based on action.
        """
        if self.action == 'list':
            return BrandListSerializer
        elif self.action == 'retrieve':
            return BrandDetailSerializer
        else:  # create, update, partial_update
            return BrandCreateUpdateSerializer

    def get_queryset(self):
        """
        Return queryset filtered by active and non-deleted brands.
        """
        qs = super().get_queryset()
        return qs

    def perform_create(self, serializer):
        """
        Save brand with created_by user.
        """
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        """
        Save brand with updated_by user.
        """
        serializer.save(updated_by=self.request.user)
