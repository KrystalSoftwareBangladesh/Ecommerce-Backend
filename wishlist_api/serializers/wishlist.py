# wishlist_api/serializers/wishlist.py
from rest_framework import serializers

from product_api.serializers import ProductListSerializer
from wishlist_api.models import Wishlist


class WishlistListSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)

    class Meta:
        model = Wishlist
        fields = (
            "id",
            "product",
            "created_at",
        )


class WishlistCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wishlist
        fields = ("product",)
