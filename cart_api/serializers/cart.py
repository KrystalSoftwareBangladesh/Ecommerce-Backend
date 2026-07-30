# cart_api/serializers/cart.py
from rest_framework import serializers

from cart_api.models import Cart
from product_api.serializers import ProductListSerializer


class CartListSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = (
            "id",
            "product",
            "quantity",
            "subtotal",
            "created_at",
        )

    def get_subtotal(self, obj):
        return obj.quantity * obj.product.current_selling_price


class CartCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cart
        fields = (
            "product",
            "quantity",
        )

    def validate_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError(
                "Quantity must be at least 1."
            )
        return value
