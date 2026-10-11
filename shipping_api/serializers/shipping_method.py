# shipping_api/serializers/shipping_method.py
from rest_framework import serializers

from shipping_api.models import ShippingMethod


class ShippingMethodListSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShippingMethod
        fields = [
            "id",
            "name",
            "code",
            "is_active",
            "display_order",
            "created_at",
        ]


class ShippingMethodDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShippingMethod
        fields = [
            "id",
            "name",
            "code",
            "description",
            "is_active",
            "display_order",
            "created_at",
            "updated_at",
        ]


class ShippingMethodCreateUpdateSerializer(
    serializers.ModelSerializer
):
    class Meta:
        model = ShippingMethod
        fields = [
            "name",
            "code",
            "description",
            "is_active",
            "display_order",
        ]

    def validate_code(self, value):
        qs = ShippingMethod.objects.filter(
            code=value
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "A method with this code already exists."
            )
        return value
