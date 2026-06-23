# product_api/views/v1/product.py
from django.db.models import Sum, Value, IntegerField
from django.db.models.functions import Coalesce
from drf_spectacular.utils import extend_schema

from rest_framework import viewsets, filters, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django_filters.rest_framework import DjangoFilterBackend
import django_filters

from product_api.models import (
    Product, ProductVariant,
)
from product_api.serializers import (
    ProductListSerializer,
    ProductDetailSerializer,
    ProductCreateUpdateSerializer,
    ProductVariantListSerializer,
    ProductVariantDetailSerializer,
    ProductVariantCreateUpdateSerializer,
)


class ProductFilter(django_filters.FilterSet):
    category = django_filters.NumberFilter(field_name='categories__id')

    class Meta:
        model = Product
        fields = ['category']


@extend_schema(tags=["Products"])
class ProductViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = ProductFilter
    search_fields = ['name']

    def get_queryset(self):
        return Product.objects.filter(
            is_active=True
        ).prefetch_related('categories').order_by('name', 'id')

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
        ).select_related('product__category').annotate(
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
