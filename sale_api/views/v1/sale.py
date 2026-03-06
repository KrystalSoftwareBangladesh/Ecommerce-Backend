# sale_api/views/v1/sale.py
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from drf_spectacular.utils import extend_schema
import django_filters
from sale_api.models import Sale
from sale_api.serializers import (
    SaleCreateSerializer, SaleUpdateSerializer, SaleListSerializer,
    SaleDetailSerializer,
)
from sale_api.services import (
    create_sale, update_sale, confirm_sale, cancel_sale
)


class SaleFilter(django_filters.FilterSet):
    start_date = django_filters.DateFilter(
        field_name='sale_date', lookup_expr='gte')
    end_date = django_filters.DateFilter(
        field_name='sale_date', lookup_expr='lte')

    class Meta:
        model = Sale
        fields = ['customer', 'channel', 'status', 'start_date', 'end_date']


@extend_schema(tags=["Sales"])
class SaleViewSet(viewsets.ModelViewSet):
    queryset = Sale.objects.none()
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = SaleFilter
    search_fields = ['invoice_number']
    ordering_fields = ['sale_date', 'total_amount']
    ordering = ['-sale_date']

    def get_queryset(self):
        qs = Sale.objects.filter(is_active=True)
        return qs.select_related('customer').prefetch_related('items')

    def get_serializer_class(self):
        if self.action == 'list':
            return SaleListSerializer
        if self.action == 'retrieve':
            return SaleDetailSerializer
        if self.action == 'create':
            return SaleCreateSerializer
        if self.action in ['update', 'partial_update']:
            return SaleUpdateSerializer
        return SaleDetailSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            sale = create_sale(
                request.user,
                serializer.validated_data
            )
        except Exception as e:
            return Response({
                'detail': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            SaleDetailSerializer(sale).data,
            status=status.HTTP_201_CREATED
        )

    def partial_update(self, request, *args, **kwargs):
        sale = self.get_object()
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            sale = update_sale(request.user, sale, serializer.validated_data)
        except Exception as e:
            return Response({
                'detail': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
        return Response(SaleDetailSerializer(sale).data)

    def destroy(self, request, *args, **kwargs):
        sale = self.get_object()
        if sale.status != 'DRAFT':
            return Response({
                'detail': 'Cannot delete non-draft sale.'
            }, status=status.HTTP_400_BAD_REQUEST)
        sale.is_active = False
        sale.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        sale = self.get_object()
        try:
            sale = confirm_sale(request.user, sale)
        except Exception as e:
            return Response({
                'detail': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
        return Response(SaleDetailSerializer(sale).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        sale = self.get_object()
        try:
            sale = cancel_sale(request.user, sale)
        except Exception as e:
            return Response({
                'detail': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
        return Response(SaleDetailSerializer(sale).data)

    @extend_schema(
        summary="List available sale channels",
        description="Returns the canonical channel values and labels for sales."
    )
    @action(detail=False, methods=['get'], url_path='channels')
    def channels(self, request):
        channels = [
            {'value': value, 'label': label}
            for value, label in Sale.SaleChannel.choices
        ]
        return Response({
            'default': Sale.SaleChannel.WALK_IN,
            'channels': channels
        })
