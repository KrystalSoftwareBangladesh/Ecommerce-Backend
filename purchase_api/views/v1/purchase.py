# purchase_api/views/v1/purchase.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
import django_filters
from django_filters import rest_framework as filters

from purchase_api.models import Purchase, PurchaseStatus
from purchase_api.serializers import (
    PurchaseListSerializer, PurchaseDetailSerializer,
    PurchaseCreateSerializer, PurchaseUpdateSerializer
)
from purchase_api.services import (
    create_purchase, update_purchase, confirm_purchase, cancel_purchase
)


class PurchaseFilter(django_filters.FilterSet):
    supplier = django_filters.NumberFilter(field_name='supplier__id')
    status = django_filters.ChoiceFilter(choices=PurchaseStatus.choices)
    purchase_date_min = filters.DateFilter(
        field_name='purchase_date', lookup_expr='gte')
    purchase_date_max = filters.DateFilter(
        field_name='purchase_date', lookup_expr='lte')

    class Meta:
        model = Purchase
        fields = ['supplier', 'status']


@extend_schema(tags=["Purchases"])
class PurchaseViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = PurchaseFilter
    search_fields = ['invoice_number']

    def get_queryset(self):
        return Purchase.objects.filter(
            is_active=True
        ).select_related('supplier').prefetch_related('items__product_variant')

    def get_serializer_class(self):
        if self.action == 'list':
            return PurchaseListSerializer
        if self.action == 'retrieve':
            return PurchaseDetailSerializer
        if self.action == 'create':
            return PurchaseCreateSerializer
        if self.action in ['update', 'partial_update']:
            return PurchaseUpdateSerializer
        return PurchaseDetailSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        purchase = create_purchase(serializer.validated_data, request.user)
        return Response(
            PurchaseDetailSerializer(purchase).data,
            status=status.HTTP_201_CREATED
        )

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(
            instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        purchase = update_purchase(
            instance, serializer.validated_data, request.user)
        return Response(PurchaseDetailSerializer(purchase).data)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        instance = self.get_object()
        try:
            purchase = confirm_purchase(instance, request.user)
            return Response(PurchaseDetailSerializer(purchase).data)
        except ValueError as e:
            return Response({
                    'detail': str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        instance = self.get_object()
        try:
            purchase = cancel_purchase(instance, request.user)
            return Response(PurchaseDetailSerializer(purchase).data)
        except ValueError as e:
            return Response({
                    'detail': str(e)
                }, status=status.HTTP_400_BAD_REQUEST
            )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status != PurchaseStatus.DRAFT:
            return Response({
                    'detail': 'Only draft purchases can be deleted.'
                }, status=status.HTTP_400_BAD_REQUEST
            )
        instance.soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
