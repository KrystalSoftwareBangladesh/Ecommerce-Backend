# shipping_api/views/v1/shipping_rate.py
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from drf_spectacular.utils import extend_schema

from shipping_api.models import ShippingRate
from shipping_api.serializers import (
    ShippingRateListSerializer,
    ShippingRateDetailSerializer,
    ShippingRateCreateUpdateSerializer,
)


@extend_schema(tags=["Shipping Rates"])
class ShippingRateViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = (
        ShippingRate.objects.filter(
            deleted_at__isnull=True,
        )
        .select_related("zone", "method")
    )

    def get_serializer_class(self):
        if self.action == "list":
            return ShippingRateListSerializer
        if self.action in (
            "create",
            "partial_update",
        ):
            return ShippingRateCreateUpdateSerializer
        return ShippingRateDetailSerializer

    def perform_create(self, serializer):
        serializer.save(
            created_by=self.request.user,
            updated_by=self.request.user,
        )

    def perform_update(self, serializer):
        serializer.save(
            updated_by=self.request.user,
        )

    def perform_destroy(self, instance):
        instance.updated_by = self.request.user
        instance.save(
            update_fields=["updated_by", "updated_at"],
        )
        instance.soft_delete()
