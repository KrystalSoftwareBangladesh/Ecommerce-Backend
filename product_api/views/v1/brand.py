# product_api/views/v1/brand.py
from rest_framework import viewsets
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.parsers import MultiPartParser, FormParser
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
    extend_schema_view,
)

from EcommerceBackend.core.permission import PublicReadPermissionMixin

from category_api.services import get_category_descendant_ids
from product_api.models import Brand
from category_api.models import Category
from product_api.serializers import (
    BrandListSerializer,
    BrandDetailSerializer,
    BrandCreateUpdateSerializer,
    BrandSummarySerializer,
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
    public_actions = PublicReadPermissionMixin.public_actions + [
        "category_brands",
    ]
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

    @extend_schema(
        summary="List brands by category",
        description=(
            "Return unique active brands associated with products "
            "belonging to the selected category or any of its descendants. "
            "The category can be identified by ID or slug."
        ),
        parameters=[
            OpenApiParameter(
                name="category_id",
                type=str,
                location=OpenApiParameter.PATH,
                required=True,
                description="Category ID or slug.",
            ),
        ],
        responses={
            200: BrandSummarySerializer(many=True),
        },
        filters=False,
    )
    @action(
        detail=False,
        methods=["get"],
        url_path=r"category/(?P<category_id>[^/.]+)",
        url_name="category-brands",
    )
    def category_brands(self, request, category_id=None):
        category_queryset = Category.objects.filter(
            deleted_at__isnull=True,
        )

        if category_id.isdigit():
            category = get_object_or_404(
                category_queryset,
                id=int(category_id),
            )
        else:
            category = get_object_or_404(
                category_queryset,
                slug=category_id,
            )

        category_ids = get_category_descendant_ids(category)

        queryset = self.get_queryset().filter(
            products__categories__id__in=category_ids,
        ).distinct()

        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = BrandSummarySerializer(
                page,
                many=True,
                context={"request": request},
            )
            return self.get_paginated_response(serializer.data)

        serializer = BrandSummarySerializer(
            queryset,
            many=True,
            context={"request": request},
        )

        return Response(serializer.data)
