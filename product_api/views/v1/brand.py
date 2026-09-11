# product_api/views/v1/brand.py
from rest_framework import viewsets
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.parsers import MultiPartParser, FormParser
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404

from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
    extend_schema_view,
)

from EcommerceBackend.core.permission import PublicReadPermissionMixin

from product_api.models import Brand
from product_api.serializers import (
    BrandListSerializer,
    BrandDetailSerializer,
    BrandCreateUpdateSerializer,
)


BRAND_LOOKUP_PARAMETER = OpenApiParameter(
    name="id",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.PATH,
    description="Brand ID or slug",
)


@extend_schema(tags=["Brands"])
@extend_schema_view(
    retrieve=extend_schema(
        parameters=[BRAND_LOOKUP_PARAMETER],
    )
)
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
    lookup_field = "id"
    lookup_url_kwarg = "id"
    lookup_value_regex = r"[^/]+"

    def get_object(self):
        lookup_value = self.kwargs[
            self.lookup_url_kwarg or self.lookup_field
        ]
        queryset = self.filter_queryset(self.get_queryset())

        if lookup_value.isdigit():
            obj = get_object_or_404(
                queryset,
                pk=int(lookup_value),
            )
        else:
            obj = get_object_or_404(
                queryset,
                slug=lookup_value,
            )

        self.check_object_permissions(self.request, obj)
        return obj

    def get_serializer_class(self):
        if self.action == 'list':
            return BrandListSerializer
        elif self.action == 'retrieve':
            return BrandDetailSerializer
        else:
            return BrandCreateUpdateSerializer
