# checkout_api/serializers/checkout.py
from rest_framework import serializers


class CheckoutValidateSerializer(
    serializers.Serializer
):
    shipping_address_id = serializers.IntegerField(
        required=True,
        help_text=(
            "ID of the customer's shipping address."
        ),
    )
    shipping_method_id = serializers.IntegerField(
        required=True,
        help_text=(
            "ID of the selected shipping method."
        ),
    )


class CheckoutCartItemSerializer(
    serializers.Serializer
):
    id = serializers.IntegerField()
    product_id = serializers.IntegerField()
    product_name = serializers.CharField()
    quantity = serializers.IntegerField()
    unit_price = serializers.DecimalField(
        max_digits=12, decimal_places=2
    )
    line_total = serializers.DecimalField(
        max_digits=12, decimal_places=2
    )


class CheckoutCartSerializer(
    serializers.Serializer
):
    id = serializers.IntegerField()
    items = CheckoutCartItemSerializer(many=True)


class CheckoutPricingSerializer(
    serializers.Serializer
):
    subtotal = serializers.DecimalField(
        max_digits=12, decimal_places=2
    )
    shipping_charge = serializers.DecimalField(
        max_digits=12, decimal_places=2
    )
    discount_total = serializers.DecimalField(
        max_digits=12, decimal_places=2
    )
    tax_total = serializers.DecimalField(
        max_digits=12, decimal_places=2
    )
    grand_total = serializers.DecimalField(
        max_digits=12, decimal_places=2
    )


class CheckoutShippingSerializer(
    serializers.Serializer
):
    address_id = serializers.IntegerField()
    method_id = serializers.IntegerField()
    method_name = serializers.CharField()
    method_code = serializers.CharField()
    zone_name = serializers.CharField()
    zone_code = serializers.CharField()
    base_charge = serializers.DecimalField(
        max_digits=12, decimal_places=2
    )
    is_free_shipping = serializers.BooleanField()
    free_shipping_threshold = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        allow_null=True,
    )


class CheckoutValidateResponseSerializer(
    serializers.Serializer
):
    is_valid = serializers.BooleanField()
    cart = CheckoutCartSerializer(
        allow_null=True
    )
    pricing = CheckoutPricingSerializer(
        allow_null=True
    )
    shipping = CheckoutShippingSerializer(
        allow_null=True
    )
    errors = serializers.ListField(
        child=serializers.CharField()
    )
