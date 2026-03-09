# supplier_api/views/v1/supplier.py
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema

import django_filters

from rest_framework import viewsets, filters, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from supplier_api.models import Supplier, PaymentType
from supplier_api.serializers import (
    SupplierListSerializer,
    SupplierDetailSerializer,
    SupplierCreateUpdateSerializer
)
from category_api.models import Category


class SupplierFilter(django_filters.FilterSet):
    category = django_filters.ModelMultipleChoiceFilter(
        field_name='categories__id',
        queryset=Category.objects.all()
    )
    payment_type = django_filters.ChoiceFilter(choices=PaymentType.choices)

    class Meta:
        model = Supplier
        fields = ['payment_type']


@extend_schema(tags=["Suppliers"])
class SupplierViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = SupplierFilter
    search_fields = ['name', 'phone', 'email']
    ordering_fields = ['name', 'created_at', 'payment_type', 'id']
    ordering = ['name', 'id']

    def get_queryset(self):
        return Supplier.objects.filter(
            is_active=True
        ).select_related(
            'created_by', 'updated_by').prefetch_related(
                'categories')

    def get_serializer_class(self):
        if self.action == 'list':
            return SupplierListSerializer
        if self.action == 'retrieve':
            return SupplierDetailSerializer
        return SupplierCreateUpdateSerializer

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
