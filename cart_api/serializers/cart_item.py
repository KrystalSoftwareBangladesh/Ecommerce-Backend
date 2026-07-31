# cart_api/serializers/cart_item.py
from rest_framework import serializers

from cart_api.models import CartItem
from cart_api.services import (
    add_cart_item,
    update_cart_item,
)
from product_api.models import Product
from product_api.serializers import ProductListSerializer


class CartItemSerializer(serializers.ModelSerializer):
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


class CartItemCreateUpdateSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(
            is_active=True,
        )
    )

    class Meta:
        model = CartItem
        fields = [
            "id",
            "product",
            "quantity",
        ]
        read_only_fields = [
            "id",
        ]

    def create(self, validated_data):
        return add_cart_item(
            user=self.context["request"].user,
            **validated_data,
        )

    def update(self, instance, validated_data):
        return update_cart_item(
            cart_item=instance,
            **validated_data,
        )
