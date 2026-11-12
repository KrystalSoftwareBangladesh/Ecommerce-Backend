# cms_api/serializers/cms_navigation.py
"""Navigation menu/item serializers (docs/cms-architecture.md 5.5, 6).

Management serializers expose the raw row shape (``page`` as an id,
``external_url`` verbatim); the public serializer resolves each item
to one ``url`` field and prunes draft/invisible content (built by
``services.navigation.resolve_navigation_tree``).
"""
from rest_framework import serializers

from cms_api.models import (
    CmsNavigationItem,
    CmsNavigationMenu,
    CmsPage,
    NavigationLinkType,
)
from cms_api.services import (
    add_navigation_item,
    create_menu,
    update_menu,
    update_navigation_item,
)


class CmsNavigationItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = CmsNavigationItem
        fields = [
            "id",
            "menu",
            "parent",
            "label",
            "link_type",
            "page",
            "external_url",
            "is_visible",
            "open_in_new_tab",
            "sort_order",
        ]
        read_only_fields = fields


class CmsNavigationItemWriteSerializer(serializers.Serializer):
    """Write shape of one navigation item.

    Exactly one of ``page``/``external_url`` must match ``link_type``
    (model XOR rule); ``parent``, if given, must belong to the same
    menu and must not create a cycle (service-layer checks).
    """

    label = serializers.CharField(max_length=255)
    link_type = serializers.ChoiceField(
        choices=NavigationLinkType.choices,
    )
    parent = serializers.PrimaryKeyRelatedField(
        queryset=CmsNavigationItem.objects.all(),
        required=False,
        allow_null=True,
    )
    page = serializers.PrimaryKeyRelatedField(
        queryset=CmsPage.objects.all(),
        required=False,
        allow_null=True,
    )
    external_url = serializers.CharField(
        required=False, allow_blank=True, max_length=500,
    )
    is_visible = serializers.BooleanField(required=False, default=True)
    open_in_new_tab = serializers.BooleanField(
        required=False, default=False,
    )

    def validate(self, attrs):
        """Validate the merged (existing + submitted) state.

        Switching ``link_type`` on an update must explicitly provide
        the new target *and* clear the old one in the same request
        (e.g. ``{"link_type": "EXTERNAL", "external_url": "...",
        "page": null}``) — a partial update never silently clears the
        field it no longer needs.
        """
        link_type = attrs.get(
            "link_type", getattr(self.instance, "link_type", None),
        )
        page_value = attrs.get(
            "page", getattr(self.instance, "page", None),
        )
        external_url_value = attrs.get(
            "external_url",
            getattr(self.instance, "external_url", ""),
        )
        if link_type == NavigationLinkType.PAGE:
            if not page_value:
                raise serializers.ValidationError({
                    "page": "page is required when link_type is PAGE.",
                })
            if external_url_value:
                raise serializers.ValidationError({
                    "external_url": (
                        "external_url must be blank when link_type "
                        "is PAGE."
                    ),
                })
        elif link_type == NavigationLinkType.EXTERNAL:
            if not external_url_value:
                raise serializers.ValidationError({
                    "external_url": (
                        "external_url is required when link_type is "
                        "EXTERNAL."
                    ),
                })
            if page_value:
                raise serializers.ValidationError({
                    "page": (
                        "page must not be set when link_type is "
                        "EXTERNAL."
                    ),
                })
        return attrs


class CmsNavigationItemCreateSerializer(CmsNavigationItemWriteSerializer):
    def create(self, validated_data):
        return add_navigation_item(
            menu=self.context["menu"],
            validated_data=validated_data,
            user=self.context["request"].user,
        )


class CmsNavigationItemUpdateSerializer(CmsNavigationItemWriteSerializer):
    label = serializers.CharField(
        max_length=255, required=False,
    )
    link_type = serializers.ChoiceField(
        choices=NavigationLinkType.choices,
        required=False,
    )

    def update(self, instance, validated_data):
        return update_navigation_item(
            menu=self.context["menu"],
            item=instance,
            validated_data=validated_data,
            user=self.context["request"].user,
        )


class CmsNavigationItemReorderSerializer(serializers.Serializer):
    parent = serializers.PrimaryKeyRelatedField(
        queryset=CmsNavigationItem.objects.all(),
        required=False,
        allow_null=True,
    )
    order = serializers.ListField(child=serializers.IntegerField())


class CmsNavigationMenuListSerializer(serializers.ModelSerializer):
    class Meta:
        model = CmsNavigationMenu
        fields = ["id", "name", "key", "is_active"]
        read_only_fields = fields


class CmsNavigationMenuDetailSerializer(CmsNavigationMenuListSerializer):
    items = CmsNavigationItemSerializer(many=True, read_only=True)

    class Meta(CmsNavigationMenuListSerializer.Meta):
        fields = CmsNavigationMenuListSerializer.Meta.fields + [
            "created_at",
            "updated_at",
            "items",
        ]
        read_only_fields = fields


class CmsNavigationMenuWriteSerializer(serializers.ModelSerializer):
    """``is_active`` is deliberately not writable here: it is the
    soft-delete flag (``SoftDeleteModel``), set only by ``DELETE``
    (``delete_menu`` -> ``soft_delete()``), so there is exactly one
    path that deactivates a menu, not two inconsistent ones."""

    class Meta:
        model = CmsNavigationMenu
        fields = ["name", "key"]


class CmsNavigationMenuCreateSerializer(CmsNavigationMenuWriteSerializer):
    def create(self, validated_data):
        return create_menu(
            validated_data=validated_data,
            user=self.context["request"].user,
        )


class CmsNavigationMenuUpdateSerializer(CmsNavigationMenuWriteSerializer):
    class Meta(CmsNavigationMenuWriteSerializer.Meta):
        extra_kwargs = {
            "name": {"required": False},
            "key": {"required": False},
        }

    def update(self, instance, validated_data):
        return update_menu(
            menu=instance,
            validated_data=validated_data,
            user=self.context["request"].user,
        )


class CmsNavigationPublicNodeSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    label = serializers.CharField(read_only=True)
    url = serializers.CharField(read_only=True)
    open_in_new_tab = serializers.BooleanField(read_only=True)
    children = serializers.SerializerMethodField()

    def get_children(self, instance):
        return CmsNavigationPublicNodeSerializer(
            instance["children"], many=True,
        ).data
