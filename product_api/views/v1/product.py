# product_api/views/v1/product.py
from django.db.models import Prefetch, Sum, Value, IntegerField, Q
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import (
    extend_schema, extend_schema_view, OpenApiParameter,
    OpenApiTypes,
)

from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django_filters.rest_framework import DjangoFilterBackend
import django_filters

from EcommerceBackend.core.permission import PublicReadPermissionMixin
from EcommerceBackend.core.models import ModerationStatus
from product_api.models import (
    Product, ProductVariant, ProductImage,
)
from review_api.models import Review
from product_api.serializers import (
    ProductListSerializer,
    ProductDetailSerializer,
    ProductCreateUpdateSerializer,
    ProductVariantListSerializer,
    ProductVariantDetailSerializer,
    ProductVariantCreateUpdateSerializer,
    ProductImageListSerializer,
)
from review_api.serializers import ReviewListSerializer


class ProductFilter(django_filters.FilterSet):
    category = django_filters.BaseInFilter(
        field_name='categories__id',
        lookup_expr='in',
    )
    categories = django_filters.BaseInFilter(
        field_name='categories__id',
        lookup_expr='in',
    )

    class Meta:
        model = Product
        fields = ['category', 'categories']


@extend_schema(tags=["Products"])
@extend_schema_view(
    retrieve=extend_schema(
        parameters=[
            OpenApiParameter(
                name="id",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.PATH,
                description="Product ID or slug",
            )
        ]
    )
)
class ProductViewSet(PublicReadPermissionMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    public_actions = PublicReadPermissionMixin.public_actions + [
        "product_variants", "product_images",
    ]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = ProductFilter
    search_fields = ['name']

    def get_object(self):
        lookup_value = self.kwargs[self.lookup_url_kwarg or self.lookup_field]

        queryset = self.filter_queryset(self.get_queryset())

        if lookup_value.isdigit():
            obj = get_object_or_404(queryset, pk=int(lookup_value))
        else:
            obj = get_object_or_404(queryset, slug=lookup_value)

        self.check_object_permissions(self.request, obj)
        return obj

    def get_queryset(self):
        default_image_qs = ProductImage.objects.filter(
            is_default=True, is_active=True, deleted_at__isnull=True,
        ).only('id', 'image', 'alt_text', 'display_order', 'is_default',
               'created_at')

        return Product.objects.filter(
            is_active=True
        ).select_related("origin"
                         ).prefetch_related(
            'categories',
            Prefetch('images', queryset=default_image_qs,
                     to_attr='_default_images'),
        ).order_by('name', 'id')

    def get_serializer_class(self):
        if self.action == 'list':
            return ProductListSerializer
        if self.action == 'retrieve':
            return ProductDetailSerializer
        return ProductCreateUpdateSerializer

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=['is_active', 'updated_at'])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['get'], url_path='product-variants')
    def product_variants(self, request, pk=None):
        product = self.get_object()
        queryset = ProductVariant.objects.filter(
            product=product,
            is_active=True,
        ).select_related('product').annotate(
            current_stock=Coalesce(
                Sum('movements__quantity'),
                Value(0),
                output_field=IntegerField()
            )
        ).order_by('sku', 'id')

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = ProductVariantListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = ProductVariantListSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='product-images')
    def product_images(self, request, pk=None):
        product = self.get_object()
        queryset = ProductImage.objects.filter(
            product=product,
            is_active=True,
            deleted_at__isnull=True,
        ).order_by('display_order', 'created_at', 'id')

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = ProductImageListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = ProductImageListSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='reviews')
    def product_reviews(self, request, pk=None):
        product = self.get_object()
        # queryset = (
        #     Review.objects.filter(
        #         product=product,
        #         is_active=True,
        #         status=ModerationStatus.APPROVED,
        #     )
        #     .select_related("created_by")
        #     .order_by('-created_at', 'id')
        # )
        queryset = (
            Review.objects.filter(
                product=product,
                is_active=True,
            )
            .filter(
                Q(status=ModerationStatus.APPROVED)
                | Q(
                    status=ModerationStatus.PENDING,
                    created_by=request.user,
                )
            )
            .select_related("created_by")
            .order_by("-created_at", "id")
        )

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = ReviewListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = ReviewListSerializer(queryset, many=True)
        return Response(serializer.data)


class VariantFilter(django_filters.FilterSet):
    product = django_filters.NumberFilter(field_name='product__id')

    class Meta:
        model = ProductVariant
        fields = ['product']


@extend_schema(tags=["Products"])
class ProductVariantViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = VariantFilter
    search_fields = ['sku', 'color', 'size', 'product__name']

    def get_queryset(self):
        return ProductVariant.objects.filter(
            is_active=True
        ).select_related('product').annotate(
            current_stock=Coalesce(
                Sum('movements__quantity'),
                Value(0),
                output_field=IntegerField()
            )
        ).order_by('sku', 'id')

    def get_serializer_class(self):
        if self.action == 'list':
            return ProductVariantListSerializer
        if self.action == 'retrieve':
            return ProductVariantDetailSerializer
        return ProductVariantCreateUpdateSerializer

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=['is_active', 'updated_at'])
        return Response(status=status.HTTP_204_NO_CONTENT)
