# review_api/serialziers/review.py
from rest_framework import serializers

from product_api.models import Product
from review_api.models import Review
from review_api.services.review import (
    create_review,
    update_review,
)
from user_api.serializers import UserSummarySerializer


class ReviewListSerializer(serializers.ModelSerializer):
    created_by = UserSummarySerializer(read_only=True)

    class Meta:
        model = Review
        fields = [
            "id",
            "rating",
            "title",
            "body",
            "is_verified_purchase",
            "created_at",
            "created_by",
        ]


class ReviewDetailSerializer(serializers.ModelSerializer):
    user = serializers.CharField(source="created_by", read_only=True)

    class Meta:
        model = Review
        fields = "__all__"
        read_only_fields = [
            "status",
            "approved_at",
            "approved_by",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "is_active",
            "deleted_at",
        ]


class ReviewCreateUpdateSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True)
    )

    class Meta:
        model = Review
        fields = [
            "id",
            "product",
            "rating",
            "title",
            "body",
        ]
        read_only_fields = ["id"]

    def create(self, validated_data):
        return create_review(
            product=validated_data.pop("product"),
            user=self.context["request"].user,
            **validated_data,
        )

    def update(self, instance, validated_data):
        return update_review(
            review=instance,
            user=self.context["request"].user,
            **validated_data,
        )
