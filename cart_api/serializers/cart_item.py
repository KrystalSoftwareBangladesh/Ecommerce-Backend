# cart_api/serializers/cart_item.py
from rest_framework import serializers

from cart_api.models import CartItem
from product_api.serializers import ProductListSerializer


class CartItemListSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)

    class Meta:
        model = CartItem
        fields = [
            "id",
            "product",
            "quantity",
            "created_at",
            "updated_at",
        ]


class CartItemDetailSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)

    class Meta:
        model = CartItem
        fields = [
            "id",
            "product",
            "quantity",
            "created_at",
            "updated_at",
        ]


class CartItemCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CartItem
        fields = [
            "product",
            "quantity",
        ]


class CartItemUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CartItem
        fields = [
            "quantity",
        ]
