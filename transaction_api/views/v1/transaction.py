import django_filters

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view

from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from transaction_api.models import AccountingTransaction, TransactionStatus
from transaction_api.serializers import (
    AccountingTransactionCreateSerializer,
    AccountingTransactionDetailSerializer,
    AccountingTransactionListSerializer,
    TransactionStatusListSerializer,
)
from transaction_api.services import (
    create_transaction,
    post_transaction,
    update_transaction,
)


class AccountingTransactionFilter(django_filters.FilterSet):
    account = django_filters.NumberFilter(field_name='lines__account__id')
    transaction_date_min = django_filters.DateFilter(
        field_name='transaction_date',
        lookup_expr='gte',
    )
    transaction_date_max = django_filters.DateFilter(
        field_name='transaction_date',
        lookup_expr='lte',
    )
    status = django_filters.ChoiceFilter(choices=TransactionStatus.choices)

    class Meta:
        model = AccountingTransaction
        fields = ['account', 'status']


@extend_schema_view(
    create=extend_schema(
        responses={201: AccountingTransactionDetailSerializer}
    ),
    partial_update=extend_schema(
        responses={200: AccountingTransactionDetailSerializer}
    ),
    post_entry=extend_schema(
        summary='Post accounting transaction',
        responses={200: AccountingTransactionDetailSerializer},
    ),
    statuses=extend_schema(
        summary='List available transaction statuses',
        responses={200: TransactionStatusListSerializer},
    ),
)
@extend_schema(tags=["Transactions"])
class AccountingTransactionViewSet(viewsets.ModelViewSet):
    queryset = AccountingTransaction.objects.none()
    permission_classes = [IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = AccountingTransactionFilter
    search_fields = [
        'transaction_no',
        'reference',
        'description',
        'lines__account__code',
        'lines__account__name',
    ]
    ordering_fields = [
        'transaction_no',
        'transaction_date',
        'status',
        'total_debit',
        'id',
    ]
    ordering = ['-transaction_date', '-id']

    def get_queryset(self):
        return AccountingTransaction.objects.filter(
            deleted_at__isnull=True
        ).select_related(
            'created_by',
            'updated_by',
        ).prefetch_related(
            'lines__account',
        ).distinct()

    def get_serializer_class(self):
        if self.action == 'list':
            return AccountingTransactionListSerializer
        if self.action == 'retrieve':
            return AccountingTransactionDetailSerializer
        if self.action in ['create', 'update', 'partial_update']:
            return AccountingTransactionCreateSerializer
        return AccountingTransactionDetailSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            accounting_transaction = create_transaction(
                request.user,
                serializer.validated_data,
            )
        except Exception as exc:
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            AccountingTransactionDetailSerializer(
                accounting_transaction
            ).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        try:
            accounting_transaction = update_transaction(
                request.user,
                instance,
                serializer.validated_data,
            )
        except Exception as exc:
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            AccountingTransactionDetailSerializer(
                accounting_transaction
            ).data
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status != TransactionStatus.DRAFT:
            return Response(
                {'detail': 'Only draft transactions can be deleted.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance.soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='post')
    def post_entry(self, request, pk=None):
        instance = self.get_object()
        try:
            accounting_transaction = post_transaction(
                request.user,
                instance,
            )
        except Exception as exc:
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            AccountingTransactionDetailSerializer(
                accounting_transaction
            ).data
        )

    @action(detail=False, methods=['get'], url_path='statuses')
    def statuses(self, request):
        statuses = [
            {'value': value, 'label': label}
            for value, label in TransactionStatus.choices
        ]
        return Response({
            'default': TransactionStatus.DRAFT,
            'statuses': statuses,
        })
