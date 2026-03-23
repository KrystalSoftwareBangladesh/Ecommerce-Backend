from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, viewsets
from rest_framework.permissions import IsAuthenticated

from sale_api.models import PaymentMethod
from sale_api.serializers import (
    PaymentMethodCreateUpdateSerializer,
    PaymentMethodDetailSerializer,
    PaymentMethodListSerializer,
)


@extend_schema(tags=["Sale Payment Methods"])
class PaymentMethodViewSet(viewsets.ModelViewSet):
    queryset = PaymentMethod.objects.none()
    permission_classes = [IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ['is_active', 'allow_account_override']
    search_fields = ['code', 'name', 'description']
    ordering_fields = ['sort_order', 'name', 'code', 'id']
    ordering = ['sort_order', 'name', 'id']

    def get_queryset(self):
        return PaymentMethod.objects.filter(
            deleted_at__isnull=True,
        ).select_related(
            'default_account',
            'created_by',
            'updated_by',
        )

    def get_serializer_class(self):
        if self.action == 'list':
            return PaymentMethodListSerializer
        if self.action == 'retrieve':
            return PaymentMethodDetailSerializer
        return PaymentMethodCreateUpdateSerializer

    def perform_create(self, serializer):
        serializer.save(
            created_by=self.request.user,
            updated_by=self.request.user,
        )

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)
