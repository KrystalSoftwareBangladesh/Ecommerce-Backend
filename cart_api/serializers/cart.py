# cart_api/serializers/cart.py
from rest_framework import serializers

from cart_api.models import Cart


class CartSerializer(serializers.ModelSerializer):
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
            "total_items",
            "total_quantity",
            "subtotal",
            "created_at",
            "updated_at",
        ]
