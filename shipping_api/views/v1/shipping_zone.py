# shipping_api/views/v1/shipping_zone.py
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema

from shipping_api.models import ShippingZone
from shipping_api.serializers import (
    ShippingZoneListSerializer,
    ShippingZoneDetailSerializer,
    ShippingZoneCreateUpdateSerializer,
    ShippingZoneOptionSerializer,
)


@extend_schema(tags=["Shipping Zones"])
class ShippingZoneViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = (
        ShippingZone.objects.filter(
            deleted_at__isnull=True,
        )
    )

    def get_serializer_class(self):
        if self.action == "list":
            return ShippingZoneListSerializer
        if self.action == "available":
            return ShippingZoneOptionSerializer
        if self.action in (
            "create",
            "partial_update",
        ):
            return ShippingZoneCreateUpdateSerializer
        return ShippingZoneDetailSerializer

    @extend_schema(
        responses={200: ShippingZoneOptionSerializer(many=True)},
        description=(
            "Active shipping zones a customer can choose as a "
            "delivery area at checkout. Not paginated."
        ),
    )
    @action(detail=False, methods=["get"], url_path="available")
    def available(self, request):
        zones = self.get_queryset().filter(is_active=True)
        serializer = self.get_serializer(zones, many=True)
        return Response(serializer.data)

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
