# cart_api/serializers/cart.py
from rest_framework import serializers

from cart_api.models import Cart
from .cart_item import CartItemSerializer


class CartSerializer(serializers.ModelSerializer):
    cart_items = CartItemSerializer(
        many=True,
        read_only=True,
    )
    total_items = serializers.IntegerField(
        read_only=True,
    )
    total_quantity = serializers.IntegerField(
        read_only=True,
    )
    subtotal = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = Cart
        fields = [
            "id",
            "status",
            "cart_items",
            "total_items",
            "total_quantity",
            "subtotal",
            "created_at",
            "updated_at",
        ]
