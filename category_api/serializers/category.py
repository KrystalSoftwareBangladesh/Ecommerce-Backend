# category_api/serializers/category.py
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from category_api.models import Category


class CategoryListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = [
            "id",
            "slug",
            "name",
            "show_in_menu",
        ]


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
            "display_order",
            "show_in_menu",
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


class CategoryCreateSerializer(serializers.ModelSerializer):
    """
    Create a category. A blank or omitted slug is generated from the name.
    """

    # `slug` and `parent` both take part in the model's unique constraints,
    # and UniqueTogetherValidator requires every constrained field to be
    # present when there is no instance, so both need an explicit default.
    slug = serializers.SlugField(
        required=False,
        allow_blank=True,
        allow_null=True,
        default=None,
    )
    parent = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.filter(deleted_at__isnull=True),
        required=False,
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
            "display_order",
            "show_in_menu",
            "parent",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]

    def create(self, validated_data):
        if not validated_data.get("slug"):
            validated_data.pop("slug", None)

        return super().create(validated_data)


class CategoryUpdateSerializer(serializers.ModelSerializer):
    """
    Update a category. Omitting a field leaves its stored value untouched,
    and a category cannot be moved inside its own subtree.
    """

    # Unlike the create serializer, `slug` and `parent` must NOT declare
    # `default=None`. On an update UniqueTogetherValidator backfills missing
    # fields from the instance, so a default would only serve to null out a
    # stored value whenever a PUT omits the field.
    slug = serializers.SlugField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    parent = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.filter(deleted_at__isnull=True),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "display_order",
            "show_in_menu",
            "parent",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]

    def validate_parent(self, parent):
        """
        Reject moves that would put a category inside its own subtree.

        A cycle detaches the whole subtree from the roots endpoint and makes
        the recursive readers (`path`, `children`) run forever.
        """
        if parent is None:
            return parent

        if parent.pk == self.instance.pk:
            raise serializers.ValidationError(
                "A category cannot be its own parent."
            )

        seen = {parent.pk}
        ancestor = parent.parent

        while ancestor is not None:
            if ancestor.pk == self.instance.pk:
                raise serializers.ValidationError(
                    "A category cannot be moved under one of its own "
                    "subcategories."
                )

            if ancestor.pk in seen:
                break

            seen.add(ancestor.pk)
            ancestor = ancestor.parent

        return parent

    def update(self, instance, validated_data):
        if "slug" in validated_data and not validated_data["slug"]:
            validated_data.pop("slug")

        return super().update(instance, validated_data)


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
            "show_in_menu",
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


class CategoryStatisticsSerializer(serializers.Serializer):
    total_categories = serializers.IntegerField()
    root_categories = serializers.IntegerField()
    sub_categories = serializers.IntegerField()
    menu_categories = serializers.IntegerField()
    sub_menu_categories = serializers.IntegerField()


class CategoryTreeListSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            "id",
            "slug",
            "name",
            "show_in_menu",
            "children",
        ]

    @extend_schema_field(serializers.ListField())
    def get_children(self, obj):
        return CategoryTreeListSerializer(
            getattr(obj, "_tree_children", []),
            many=True,
            read_only=True,
        ).data


class CategoryNavigationSerializer(serializers.ModelSerializer):
    has_children = serializers.BooleanField(read_only=True)

    class Meta:
        model = Category
        fields = [
            "id",
            "slug",
            "name",
            "show_in_menu",
            "has_children",
        ]


class CategoryBulkMenuUpdateSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=False,
    )
    slugs = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=False,
    )
    select_all = serializers.BooleanField(
        required=False,
        default=False,
    )
    filters = serializers.DictField(
        required=False,
    )
    show_in_menu = serializers.BooleanField()

    def validate(self, attrs):
        ids = attrs.get("ids")
        slugs = attrs.get("slugs")
        select_all = attrs.get("select_all", False)

        if select_all and (ids or slugs):
            raise serializers.ValidationError(
                "select_all cannot be used with ids or slugs."
            )
        if not select_all and not ids and not slugs:
            raise serializers.ValidationError(
                "At least one of ids, slugs, or select_all=true is required."
            )

        return attrs


class CategoryBulkMenuUpdateResponseSerializer(serializers.Serializer):
    updated_count = serializers.IntegerField()
    show_in_menu = serializers.BooleanField()


class CategoryPathSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = [
            "id",
            "slug",
            "name",
        ]


class CategoryPathResponseSerializer(serializers.Serializer):
    path = CategoryPathSerializer(many=True)
