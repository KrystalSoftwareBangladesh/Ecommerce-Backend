# shipping_api/serializers/shipping_rate.py
from rest_framework import serializers

from shipping_api.models import ShippingRate


class ShippingRateListSerializer(serializers.ModelSerializer):
    zone_name = serializers.CharField(
        source="zone.name", read_only=True
    )
    method_name = serializers.CharField(
        source="method.name", read_only=True
    )

    class Meta:
        model = ShippingRate
        fields = [
            "id",
            "zone",
            "zone_name",
            "method",
            "method_name",
            "base_charge",
            "free_shipping_threshold",
            "is_active",
            "created_at",
        ]


class ShippingRateDetailSerializer(serializers.ModelSerializer):
    zone_name = serializers.CharField(
        source="zone.name", read_only=True
    )
    method_name = serializers.CharField(
        source="method.name", read_only=True
    )

    class Meta:
        model = ShippingRate
        fields = [
            "id",
            "zone",
            "zone_name",
            "method",
            "method_name",
            "base_charge",
            "free_shipping_threshold",
            "is_active",
            "created_at",
            "updated_at",
        ]


class ShippingRateCreateUpdateSerializer(
    serializers.ModelSerializer
):
    class Meta:
        model = ShippingRate
        fields = [
            "zone",
            "method",
            "base_charge",
            "free_shipping_threshold",
            "is_active",
        ]

    def validate(self, attrs):
        zone = attrs.get("zone", getattr(
            self.instance, "zone", None
        ))
        method = attrs.get("method", getattr(
            self.instance, "method", None
        ))
        is_active = attrs.get("is_active", getattr(
            self.instance, "is_active", True
        ))

        if is_active and zone and method:
            qs = ShippingRate.objects.filter(
                zone=zone,
                method=method,
                is_active=True,
                deleted_at__isnull=True,
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    "An active rate for this zone and "
                    "method already exists."
                )

        base_charge = attrs.get(
            "base_charge",
            getattr(self.instance, "base_charge", None),
        )
        if base_charge is not None and base_charge < 0:
            raise serializers.ValidationError(
                "base_charge must be >= 0."
            )

        threshold = attrs.get(
            "free_shipping_threshold",
            getattr(
                self.instance,
                "free_shipping_threshold",
                None,
            ),
        )
        if threshold is not None and threshold < 0:
            raise serializers.ValidationError(
                "free_shipping_threshold must be >= 0."
            )

        return attrs
