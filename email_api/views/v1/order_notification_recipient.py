# email_api/views/v1/order_notification_recipient.py
from django_filters.rest_framework import DjangoFilterBackend

from drf_spectacular.utils import extend_schema

from rest_framework import filters, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from EcommerceBackend.core.permission import ModelPermissionAccess

from email_api.models import OrderNotificationRecipient
from email_api.serializers import (
    OrderNotificationRecipientDetailSerializer,
    OrderNotificationRecipientListSerializer,
    OrderNotificationRecipientWriteSerializer,
)
from email_api.services.order_notification import (
    delete_order_notification_recipient,
)


@extend_schema(tags=["Email"])
class OrderNotificationRecipientViewSet(viewsets.ModelViewSet):
    """
    Internal addresses notified when an order is placed or cancelled.

    Every action is driven by Django model permissions.
    """
    permission_classes = [IsAuthenticated, ModelPermissionAccess]
    queryset = OrderNotificationRecipient.objects.filter(
        deleted_at__isnull=True,
    )
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ['is_active']
    search_fields = ['email', 'name']
    ordering_fields = ['email', 'name', 'created_at', 'id']
    ordering = ['email', 'id']

    def get_queryset(self):
        return OrderNotificationRecipient.objects.filter(
            deleted_at__isnull=True,
        ).select_related('created_by', 'updated_by')

    def get_serializer_class(self):
        if self.action == 'list':
            return OrderNotificationRecipientListSerializer
        if self.action in ['create', 'update', 'partial_update']:
            return OrderNotificationRecipientWriteSerializer
        return OrderNotificationRecipientDetailSerializer

    def _detail_response(self, recipient, response_status):
        return Response(
            OrderNotificationRecipientDetailSerializer(
                recipient,
                context=self.get_serializer_context(),
            ).data,
            status=response_status,
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        recipient = serializer.save()
        return self._detail_response(recipient, status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        recipient = self.get_object()
        serializer = self.get_serializer(
            recipient,
            data=request.data,
            partial=kwargs.pop('partial', False),
        )
        serializer.is_valid(raise_exception=True)
        recipient = serializer.save()
        return self._detail_response(recipient, status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        recipient = self.get_object()
        delete_order_notification_recipient(
            recipient=recipient,
            user=request.user,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
