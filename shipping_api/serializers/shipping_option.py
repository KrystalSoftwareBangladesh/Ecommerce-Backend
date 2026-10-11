# shipping_api/serializers/shipping_option.py
from rest_framework import serializers


class ShippingZoneSummarySerializer(
    serializers.Serializer
):
    id = serializers.IntegerField()
    name = serializers.CharField()
    code = serializers.CharField()


class ShippingOptionSerializer(serializers.Serializer):
    shipping_method_id = serializers.IntegerField()
    shipping_method_name = serializers.CharField()
    shipping_method_code = serializers.CharField()
    base_charge = serializers.DecimalField(
        max_digits=12, decimal_places=2
    )
    shipping_charge = serializers.DecimalField(
        max_digits=12, decimal_places=2
    )
    is_free_shipping = serializers.BooleanField()
    free_shipping_threshold = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        allow_null=True,
        required=False,
    )
    zone_name = serializers.CharField()
    zone_code = serializers.CharField()


class ShippingOptionResponseSerializer(
    serializers.Serializer
):
    zone = ShippingZoneSummarySerializer()
    cart_subtotal = serializers.DecimalField(
        max_digits=12, decimal_places=2
    )
    options = ShippingOptionSerializer(many=True)
