# category_api/serializers/category.py
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from category_api.models import Category


class CategoryListSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            "id",
            "slug",
            "name",
            "children",
        ]

    @extend_schema_field(serializers.ListField())
    def get_children(self, obj):
        children = obj.subcategories.filter(
            deleted_at__isnull=True
        )

        return CategoryListSerializer(
            children,
            many=True,
            read_only=True,
        ).data


class CategorySerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(
        required=False,
        allow_blank=True,
        allow_null=True,
        default=None,
    )
    children = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "order",
            "parent",
            "children",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]

    def validate_parent(self, parent):
        if not parent:
            return parent

        return parent

    def validate(self, attrs):
        """
        Validate category data.
        """
        return attrs

    def create(self, validated_data):
        slug = validated_data.get("slug")
        if not slug:
            validated_data.pop("slug", None)

        return super().create(validated_data)

    @extend_schema_field(serializers.ListField())
    def get_children(self, obj):
        """
        Recursively serialize direct children categories.
        Children are prefetched in viewset to avoid N+1 queries.
        """
        children = obj.subcategories.filter(deleted_at__isnull=True)
        return CategorySerializer(
            children,
            many=True,
            read_only=True
        ).data


class CategoryDetailsSerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(
        required=False,
        allow_blank=True,
        allow_null=True,
        default=None,
    )

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]


class CategorySummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
        ]


class CategoryTreeListSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            "id",
            "slug",
            "name",
            "children",
        ]

    @extend_schema_field(serializers.ListField())
    def get_children(self, obj):
        return CategoryTreeListSerializer(
            getattr(obj, "_tree_children", []),
            many=True,
            read_only=True,
        ).data
