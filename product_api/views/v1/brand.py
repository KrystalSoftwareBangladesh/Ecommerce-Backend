# product_api/views/v1/brand.py
from rest_framework import viewsets
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.parsers import MultiPartParser, FormParser
from django_filters.rest_framework import DjangoFilterBackend

from drf_spectacular.utils import extend_schema

from EcommerceBackend.core.permission import PublicReadPermissionMixin

from product_api.models import Brand
from product_api.serializers import (
    BrandListSerializer,
    BrandDetailSerializer,
    BrandCreateUpdateSerializer,
)


@extend_schema(tags=["Brands"])
class BrandViewSet(PublicReadPermissionMixin, viewsets.ModelViewSet):
    queryset = Brand.objects.filter(is_active=True, deleted_at__isnull=True)
    parser_classes = [
        MultiPartParser,
        FormParser,
    ]
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
        "display_order",
        "name",
        "created_at",
        "id",
    ]
    ordering = ["display_order", "id"]

    def get_serializer_class(self):
        if self.action == 'list':
            return BrandListSerializer
        elif self.action == 'retrieve':
            return BrandDetailSerializer
        else:
            return BrandCreateUpdateSerializer
