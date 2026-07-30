# cart_api/serializers/cart.py
from rest_framework import serializers

from cart_api.models import Cart
from cart_api.serializers.cart_type import CartTypeSerializer


class CartListSerializer(serializers.ModelSerializer):
    type = CartTypeSerializer(read_only=True)
    total_items = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = [
            "id",
            "name",
            "type",
            "status",
            "is_default",
            "total_items",
            "created_at",
            "updated_at",
        ]

    def get_total_items(self, obj):
        return obj.items.filter(
            is_active=True,
        ).count()


class CartDetailSerializer(serializers.ModelSerializer):
    type = CartTypeSerializer(read_only=True)
    total_items = serializers.SerializerMethodField()
    total_quantity = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = [
            "id",
            "name",
            "type",
            "status",
            "is_default",
            "total_items",
            "total_quantity",
            "created_at",
            "updated_at",
        ]

    def get_total_items(self, obj):
        return obj.items.filter(
            is_active=True,
        ).count()

    def get_total_quantity(self, obj):
        return (
            obj.items.filter(
                is_active=True,
            )
            .values_list(
                "quantity",
                flat=True,
            )
        ).count()


class CartCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cart
        fields = [
            "name",
            "type",
        ]


class CartUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cart
        fields = [
            "name",
            "type",
            "is_default",
        ]
