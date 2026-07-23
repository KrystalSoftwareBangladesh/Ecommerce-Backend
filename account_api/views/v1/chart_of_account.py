# accounting_api/views/v1/chart_of_account.py
from django.db import transaction
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view

from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from account_api.filters import ChartOfAccountFilter
from account_api.models import ChartOfAccount
from account_api.serializers import (
    ChartOfAccountCreateUpdateSerializer,
    ChartOfAccountDetailSerializer,
    ChartOfAccountListSerializer,
    ChartOfAccountOpeningBalanceSerializer,
)
from account_api.services import set_opening_balance


@extend_schema_view(
    create=extend_schema(
        responses={201: ChartOfAccountDetailSerializer}
    ),
    partial_update=extend_schema(
        responses={200: ChartOfAccountDetailSerializer}
    ),
)
@extend_schema(tags=["Accounts"])
class ChartOfAccountViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = ChartOfAccountFilter
    search_fields = ['code', 'name', 'description']
    ordering_fields = ['code', 'name', 'created_at', 'id']
    ordering = ['code', 'id']

    def get_queryset(self):
        return ChartOfAccount.objects.filter(
            deleted_at__isnull=True
        ).select_related(
            'parent',
            'opening_transaction',
            'created_by',
            'updated_by',
        )

    def get_serializer_class(self):
        if self.action == 'list':
            return ChartOfAccountListSerializer
        if self.action == 'retrieve':
            return ChartOfAccountDetailSerializer
        if self.action == 'set_opening_balance':
            return ChartOfAccountOpeningBalanceSerializer
        return ChartOfAccountCreateUpdateSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        opening_balance = serializer.validated_data.pop(
            'opening_balance',
            None,
        )
        opening_date = serializer.validated_data.pop('opening_date', None)
        contra_account = serializer.validated_data.pop(
            'opening_contra_account',
            None,
        )

        try:
            with transaction.atomic():
                account = serializer.save(
                    created_by=request.user,
                    updated_by=request.user,
                )
                if opening_balance is not None:
                    account = set_opening_balance(
                        account=account,
                        amount=opening_balance,
                        date=opening_date,
                        user=request.user,
                        contra_account=contra_account,
                    )
        except Exception as exc:
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            ChartOfAccountDetailSerializer(
                account,
                context=self.get_serializer_context(),
            ).data,
            status=status.HTTP_201_CREATED,
        )

    def perform_create(self, serializer):
        serializer.save(
            created_by=self.request.user,
            updated_by=self.request.user,
        )

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        account = serializer.save(updated_by=request.user)
        return Response(
            ChartOfAccountDetailSerializer(
                account,
                context=self.get_serializer_context(),
            ).data
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.updated_by = request.user
        instance.is_active = False
        instance.deleted_at = timezone.now()
        instance.save(update_fields=[
            'updated_by',
            'is_active',
            'deleted_at',
            'updated_at',
        ])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='set-opening-balance')
    def set_opening_balance(self, request, pk=None):
        account = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            account = set_opening_balance(
                account=account,
                amount=serializer.validated_data['amount'],
                date=serializer.validated_data['date'],
                user=request.user,
                contra_account=serializer.validated_data.get('contra_account'),
            )
        except Exception as exc:
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            ChartOfAccountDetailSerializer(
                account,
                context=self.get_serializer_context(),
            ).data,
            status=status.HTTP_200_OK,
        )
