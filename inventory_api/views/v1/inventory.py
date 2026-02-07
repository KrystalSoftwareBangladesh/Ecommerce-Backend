# inventory_api/views/v1/inventory.py
from rest_framework import viewsets, filters
from rest_framework.mixins import (
    CreateModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
)
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema

import django_filters

from inventory_api.models import InventoryMovement
from inventory_api.serializers import InventoryMovementSerializer


class InventoryMovementFilter(django_filters.FilterSet):
    product = django_filters.NumberFilter(
        field_name='product_variant__product__id')
    variant = django_filters.NumberFilter(field_name='product_variant__id')

    class Meta:
        model = InventoryMovement
        fields = ['movement_type', 'product', 'variant']


@extend_schema(tags=["Inventory Movement"])
class InventoryMovementViewSet(CreateModelMixin, ListModelMixin, RetrieveModelMixin, viewsets.GenericViewSet):    # noqa
    serializer_class = InventoryMovementSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = InventoryMovementFilter
    ordering_fields = ['created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        return InventoryMovement.objects.all().select_related(
            'product_variant__product', 'created_by'
        )

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
