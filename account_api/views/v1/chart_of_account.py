from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema

from rest_framework import filters, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from account_api.filters import ChartOfAccountFilter
from account_api.models import ChartOfAccount
from account_api.serializers import (
    ChartOfAccountCreateUpdateSerializer,
    ChartOfAccountDetailSerializer,
    ChartOfAccountListSerializer,
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
            'created_by',
            'updated_by',
        )

    def get_serializer_class(self):
        if self.action == 'list':
            return ChartOfAccountListSerializer
        if self.action == 'retrieve':
            return ChartOfAccountDetailSerializer
        return ChartOfAccountCreateUpdateSerializer

    def perform_create(self, serializer):
        serializer.save(
            created_by=self.request.user,
            updated_by=self.request.user,
        )

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

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
