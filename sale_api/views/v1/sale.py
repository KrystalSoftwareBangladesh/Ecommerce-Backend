# sale_api/views/v1/sale.py
import logging
from django.core.exceptions import ValidationError as DjangoValidationError
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from drf_spectacular.utils import (
    extend_schema, extend_schema_view, OpenApiParameter,
)
import django_filters
import logging
from sale_api.models import Sale, SaleStatus, get_next_sale_statuses
from sale_api.serializers import (
    SaleCreateSerializer, SaleUpdateSerializer, SaleListSerializer,
    SaleDetailSerializer, SaleChannelListSerializer, SaleStatusListSerializer,
    SaleStatusUpdateSerializer, SaleCountSummarySerializer,
    SaleAmountSummarySerializer, SalePendingCountSerializer,
    SalePerformanceReportQuerySerializer,
    SalePerformanceReportSerializer,
)
from sale_api.services import (
    create_sale, update_sale, update_sale_status,
    mark_cod_payment_collected,
)
from EcommerceBackend.core.permission import CustomPermissionAccessMixin

logger = logging.getLogger(__name__)


def _growth_percentage(current_value, previous_value):
    if not previous_value:
        return None
    growth = (
        (Decimal(current_value) - Decimal(previous_value))
        / Decimal(previous_value) * 100
    )
    return float(growth.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


class SaleFilter(django_filters.FilterSet):
    start_date = django_filters.DateFilter(
        field_name='sale_date', lookup_expr='gte')
    end_date = django_filters.DateFilter(
        field_name='sale_date', lookup_expr='lte')

    class Meta:
        model = Sale
        fields = ['customer', 'channel', 'status', 'start_date', 'end_date']


@extend_schema_view(
    create=extend_schema(responses={201: SaleDetailSerializer}),
    partial_update=extend_schema(responses={200: SaleDetailSerializer}),
    update_status=extend_schema(
        summary="Update sale status",
        request=SaleStatusUpdateSerializer,
        responses={200: SaleDetailSerializer},
    ),
    channels=extend_schema(
        summary="List available sale channels",
        description="Returns the canonical channel values and labels for sales.",  # noqa: E501
        responses={200: SaleChannelListSerializer}
    ),
    statuses=extend_schema(
        summary="List available sale statuses",
        description="Returns the canonical sale statuses and allowed next-step transitions.",  # noqa: E501
        responses={200: SaleStatusListSerializer}
    )
)
@extend_schema(tags=["Sales"])
class SaleViewSet(CustomPermissionAccessMixin, viewsets.ModelViewSet):
    custom_permissions = {
        'mark_cod_paid': 'collect_sale_payment',
    }
    queryset = Sale.objects.none()
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = SaleFilter
    search_fields = ['invoice_number']
    ordering_fields = ['sale_date', 'total_amount', 'id']
    ordering = ['-sale_date', '-id']

    def get_queryset(self):
        qs = Sale.objects.filter(is_active=True)
        return qs.select_related(
            'customer',
            'payment_method',
            'account',
            'accounting_transaction',
            'return_transaction',
        ).prefetch_related('items')

    def get_serializer_class(self):
        if self.action == 'list':
            return SaleListSerializer
        if self.action == 'retrieve':
            return SaleDetailSerializer
        if self.action == 'create':
            return SaleCreateSerializer
        if self.action in ['update', 'partial_update']:
            return SaleUpdateSerializer
        if self.action == 'update_status':
            return SaleStatusUpdateSerializer
        return SaleDetailSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            sale = create_sale(
                request.user,
                serializer.validated_data
            )
        except (DjangoValidationError, DRFValidationError):
            logger.warning(
                "Sale creation failed due to validation error.",
                exc_info=True
            )
            return Response({
                'detail': 'Invalid sale data provided.'
            }, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            SaleDetailSerializer(sale).data,
            status=status.HTTP_201_CREATED
        )

    def partial_update(self, request, *args, **kwargs):
        sale = self.get_object()
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        validated_data = dict(serializer.validated_data)
        next_status = validated_data.pop('status', None)
        account = validated_data.get('account')
        payment_method = validated_data.get('payment_method')
        try:
            if validated_data:
                sale = update_sale(request.user, sale, validated_data)
            if next_status is not None:
                sale = update_sale_status(
                    request.user,
                    sale,
                    next_status,
                    account=account,
                    payment_method=payment_method,
                )
        except (DjangoValidationError, DRFValidationError):
            return Response({
                'detail': 'Invalid request data.'
            }, status=status.HTTP_400_BAD_REQUEST)
        return Response(SaleDetailSerializer(sale).data)

    def destroy(self, request, *args, **kwargs):
        sale = self.get_object()
        if sale.status != SaleStatus.PENDING:
            return Response({
                'detail': 'Cannot delete sale unless status is pending.'
            }, status=status.HTTP_400_BAD_REQUEST)
        sale.is_active = False
        sale.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='update-status')
    def update_status(self, request, pk=None):
        sale = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            sale = update_sale_status(
                request.user,
                sale,
                serializer.validated_data['status'],
                account=serializer.validated_data.get('account'),
                payment_method=serializer.validated_data.get('payment_method'),
            )
        except (DjangoValidationError, DRFValidationError):
            return Response({
                'detail': 'Invalid request data.'
            }, status=status.HTTP_400_BAD_REQUEST)
        return Response(SaleDetailSerializer(sale).data)

    @action(
        detail=True,
        methods=['post'],
        url_path='mark-paid',
    )
    def mark_cod_paid(self, request, pk=None):
        sale = self.get_object()
        try:
            sale = mark_cod_payment_collected(
                request.user,
                sale,
            )
        except (DjangoValidationError, DRFValidationError) as exc:
            logger.warning(
                'Validation error while marking COD payment as collected.',
                exc_info=True,
            )
            return Response(
                {'detail': 'Unable to mark payment as collected.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({
            'id': sale.id,
            'status': sale.status,
            'payment_status': sale.payment_status,
            'message': 'Payment collected.',
        })

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

    @action(detail=False, methods=['get'], url_path='statuses')
    def statuses(self, request):
        statuses = [
            {'value': value, 'label': label}
            for value, label in SaleStatus.choices
        ]
        transitions = {
            status_value: get_next_sale_statuses(status_value)
            for status_value, _ in SaleStatus.choices
        }
        return Response({
            'default': SaleStatus.PENDING,
            'statuses': statuses,
            'transitions': transitions,
        })

    @extend_schema(
        tags=["Sales"],
        summary="Sale count summary",
        description="Number of sales grouped by status.",
        request=None,
        responses={200: SaleCountSummarySerializer},
    )
    @action(
        detail=False,
        methods=['get'],
        url_path='summary',
        pagination_class=None,
    )
    def summary(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        rows = queryset.order_by().values('status').annotate(
            count=Count('id')
        )
        counts = {value: 0 for value, _ in SaleStatus.choices}
        counts.update({row['status']: row['count'] for row in rows})
        serializer = SaleCountSummarySerializer({
            'success': True,
            'data': counts,
        })
        return Response(serializer.data)

    @extend_schema(
        tags=["Sales"],
        summary="Sale amount summary",
        description="Sum of total_amount grouped by status.",
        request=None,
        responses={200: SaleAmountSummarySerializer},
    )
    @action(
        detail=False,
        methods=['get'],
        url_path='amount-summary',
        pagination_class=None,
    )
    def amount_summary(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        rows = queryset.order_by().values('status').annotate(
            total=Sum('total_amount')
        )
        amounts = {
            value: Decimal('0.00') for value, _ in SaleStatus.choices
        }
        amounts.update({
            row['status']: row['total'] for row in rows
            if row['total'] is not None
        })
        serializer = SaleAmountSummarySerializer({
            'success': True,
            'data': amounts,
        })
        return Response(serializer.data)

    @extend_schema(
        tags=["Sales"],
        summary="Sale pending count",
        description=(
            "Count of active sales currently in PENDING status."
        ),
        request=None,
        responses={200: SalePendingCountSerializer},
    )
    @action(
        detail=False,
        methods=['get'],
        url_path='pending-count',
        pagination_class=None,
    )
    def pending_count(self, request):
        count = Sale.objects.filter(
            is_active=True,
            status=SaleStatus.PENDING,
        ).aggregate(pending_orders=Count('id'))['pending_orders']
        serializer = SalePendingCountSerializer({
            'success': True,
            'data': {'pending_orders': count},
        })
        return Response(serializer.data)

    @extend_schema(
        tags=["Sales"],
        summary="Sales performance report",
        description=(
            "Order and revenue totals for a reporting period ending "
            "today, compared against the immediately preceding period "
            "of equal duration, plus a zero-filled daily trend."
        ),
        parameters=[
            OpenApiParameter(
                name="days",
                type=int,
                required=False,
                description=(
                    "Reporting period length in days. Default 90, "
                    "maximum 365."
                ),
            ),
            OpenApiParameter(
                name="channel",
                type=str,
                required=False,
                enum=[value for value, _ in Sale.SaleChannel.choices],
            ),
            OpenApiParameter(
                name="customer",
                type=int,
                required=False,
                description="Customer ID.",
            ),
            OpenApiParameter(
                name="status",
                type=str,
                required=False,
                enum=[value for value, _ in SaleStatus.choices],
            ),
        ],
        request=None,
        responses={200: SalePerformanceReportSerializer},
    )
    @action(
        detail=False,
        methods=['get'],
        url_path='reports/performance',
        filter_backends=[],
        pagination_class=None,
    )
    def performance_report(self, request):
        query_serializer = SalePerformanceReportQuerySerializer(
            data=request.query_params
        )
        query_serializer.is_valid(raise_exception=True)
        days = query_serializer.validated_data['days']

        base_queryset = Sale.objects.filter(is_active=True)
        sale_filter = SaleFilter(
            data={
                key: value
                for key in ('channel', 'customer', 'status')
                if (value := request.query_params.get(key))
            },
            queryset=base_queryset,
            request=request,
        )
        if not sale_filter.is_valid():
            raise DRFValidationError(sale_filter.errors)
        filtered_queryset = sale_filter.qs

        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days - 1)
        previous_end_date = start_date - timedelta(days=1)
        previous_start_date = previous_end_date - timedelta(days=days - 1)

        current_qs = filtered_queryset.filter(
            sale_date__gte=start_date, sale_date__lte=end_date
        )
        previous_qs = filtered_queryset.filter(
            sale_date__gte=previous_start_date,
            sale_date__lte=previous_end_date,
        )

        current_totals = current_qs.aggregate(
            total_orders=Count('id'), total_revenue=Sum('total_amount')
        )
        previous_totals = previous_qs.aggregate(
            total_orders=Count('id'), total_revenue=Sum('total_amount')
        )

        total_orders = current_totals['total_orders'] or 0
        total_revenue = (
            current_totals['total_revenue'] or Decimal('0.00')
        )
        average_order_value = (
            (total_revenue / total_orders).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
            if total_orders else Decimal('0.00')
        )

        previous_period_orders = previous_totals['total_orders'] or 0
        previous_period_revenue = (
            previous_totals['total_revenue'] or Decimal('0.00')
        )

        daily_rows = current_qs.order_by().values('sale_date').annotate(
            order_count=Count('id'), revenue=Sum('total_amount')
        )
        daily_map = {row['sale_date']: row for row in daily_rows}
        daily_trend = []
        cursor = start_date
        while cursor <= end_date:
            row = daily_map.get(cursor)
            daily_trend.append({
                'date': cursor,
                'order_count': row['order_count'] if row else 0,
                'revenue': row['revenue'] if row else Decimal('0.00'),
            })
            cursor += timedelta(days=1)

        serializer = SalePerformanceReportSerializer({
            'success': True,
            'data': {
                'period': {
                    'days': days,
                    'start_date': start_date,
                    'end_date': end_date,
                },
                'overview': {
                    'total_orders': total_orders,
                    'total_revenue': total_revenue,
                    'average_order_value': average_order_value,
                },
                'comparison': {
                    'previous_period_orders': previous_period_orders,
                    'order_growth_percentage': _growth_percentage(
                        total_orders, previous_period_orders
                    ),
                    'previous_period_revenue': previous_period_revenue,
                    'revenue_growth_percentage': _growth_percentage(
                        total_revenue, previous_period_revenue
                    ),
                },
                'daily_trend': daily_trend,
            },
        })
        return Response(serializer.data)
