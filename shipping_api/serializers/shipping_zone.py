# shipping_api/serializers/shipping_zone.py
from rest_framework import serializers

from shipping_api.models import ShippingZone


class ShippingZoneListSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShippingZone
        fields = [
            "id",
            "name",
            "code",
            "is_default",
            "is_active",
            "display_order",
            "created_at",
        ]


class ShippingZoneOptionSerializer(serializers.ModelSerializer):
    """Storefront-facing zone, used to pick a delivery area."""

    class Meta:
        model = ShippingZone
        fields = [
            "id",
            "name",
            "code",
            "description",
            "is_default",
            "display_order",
        ]


class ShippingZoneDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShippingZone
        fields = [
            "id",
            "name",
            "code",
            "description",
            "is_default",
            "is_active",
            "display_order",
            "created_at",
            "updated_at",
        ]


class ShippingZoneCreateUpdateSerializer(
    serializers.ModelSerializer
):
    class Meta:
        model = ShippingZone
        fields = [
            "name",
            "code",
            "description",
            "is_default",
            "is_active",
            "display_order",
        ]

    def validate_code(self, value):
        qs = ShippingZone.objects.filter(
            code=value
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "A zone with this code already exists."
            )
        return value
