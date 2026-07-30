# cart_api/serializers/cart_type.py
from rest_framework import serializers

from cart_api.models import CartType


class CartTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CartType
        fields = [
            "id",
            "name",
            "slug",
            "description",
        ]
        read_only_fields = [
            "id",
            "slug",
        ]


class CartTypeCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CartType
        fields = [
            "name",
            "description",
        ]
