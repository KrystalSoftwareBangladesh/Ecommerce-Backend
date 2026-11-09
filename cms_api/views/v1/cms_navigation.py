# cms_api/views/v1/cms_navigation.py
"""Navigation management and public read APIs (docs/cms-architecture.md
5.5, 6, 8).

``manage_cms_navigation`` is the single permission for every
management action here (menu and item CRUD alike) — unlike
``CmsPageViewSet``/``CmsSectionViewSet``, there is no per-action
``custom_permissions`` split, matching §8's "all nav ops" row.
"""
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from cms_api.models import CmsNavigationMenu
from cms_api.serializers.cms_navigation import (
    CmsNavigationItemCreateSerializer,
    CmsNavigationItemReorderSerializer,
    CmsNavigationItemSerializer,
    CmsNavigationItemUpdateSerializer,
    CmsNavigationMenuCreateSerializer,
    CmsNavigationMenuDetailSerializer,
    CmsNavigationMenuListSerializer,
    CmsNavigationMenuUpdateSerializer,
    CmsNavigationPublicNodeSerializer,
)
from cms_api.services import (
    delete_menu,
    get_navigation_item,
    remove_navigation_item,
    reorder_navigation_items,
    resolve_navigation_tree,
)


class CmsNavigationPermission(permissions.BasePermission):
    """``cms.navigation.manage`` (§8): one permission for every
    navigation operation."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.has_perm("cms_api.manage_cms_navigation")
        )


@extend_schema(tags=["CMS Navigation"])
class CmsNavigationMenuViewSet(viewsets.ModelViewSet):
    """Menu CRUD plus item sub-resource management.

    ``DELETE`` soft-deletes the menu (``is_active=False``), which also
    removes it from every read, management or public — there is no
    restore action for navigation (spec gives none).
    """

    permission_classes = [CmsNavigationPermission]
    queryset = CmsNavigationMenu.objects.filter(
        is_active=True,
    ).prefetch_related("items")

    def get_serializer_class(self):
        if self.action == "list":
            return CmsNavigationMenuListSerializer
        if self.action == "create":
            return CmsNavigationMenuCreateSerializer
        if self.action in ("update", "partial_update"):
            return CmsNavigationMenuUpdateSerializer
        return CmsNavigationMenuDetailSerializer

    def _detail_response(
        self, response_status=status.HTTP_200_OK, instance=None,
    ):
        if instance is None:
            instance = self.get_object()
        return Response(
            CmsNavigationMenuDetailSerializer(instance).data,
            status=response_status,
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return self._detail_response(
            status.HTTP_201_CREATED, instance=serializer.instance,
        )

    def update(self, request, *args, **kwargs):
        super().update(request, *args, **kwargs)
        return self._detail_response()

    def destroy(self, request, *args, **kwargs):
        menu = self.get_object()
        delete_menu(menu=menu, user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        request=CmsNavigationItemCreateSerializer,
        responses=CmsNavigationItemSerializer,
    )
    @action(detail=True, methods=["post"], url_path="items")
    def add_item(self, request, pk=None):
        menu = self.get_object()
        serializer = CmsNavigationItemCreateSerializer(
            data=request.data,
            context={"request": request, "menu": menu},
        )
        serializer.is_valid(raise_exception=True)
        item = serializer.save()
        return Response(
            CmsNavigationItemSerializer(item).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        request=CmsNavigationItemUpdateSerializer,
        responses=CmsNavigationItemSerializer,
    )
    @action(
        detail=True,
        methods=["get", "patch", "delete"],
        url_path=r"items/(?P<item_id>[0-9]+)",
    )
    def item_row(self, request, pk=None, item_id=None):
        menu = self.get_object()
        item = get_navigation_item(menu, item_id)
        if request.method == "DELETE":
            remove_navigation_item(
                menu=menu, item=item, user=request.user,
            )
            return Response(status=status.HTTP_204_NO_CONTENT)
        if request.method == "PATCH":
            serializer = CmsNavigationItemUpdateSerializer(
                item,
                data=request.data,
                partial=True,
                context={"request": request, "menu": menu},
            )
            serializer.is_valid(raise_exception=True)
            item = serializer.save()
        return Response(CmsNavigationItemSerializer(item).data)

    @extend_schema(
        request=CmsNavigationItemReorderSerializer,
        responses=CmsNavigationItemSerializer(many=True),
    )
    @action(
        detail=True, methods=["put"], url_path="items/reorder",
    )
    def reorder_items(self, request, pk=None):
        menu = self.get_object()
        serializer = CmsNavigationItemReorderSerializer(
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)
        parent = serializer.validated_data.get("parent")
        reorder_navigation_items(
            menu=menu,
            parent_id=parent.pk if parent else None,
            order=serializer.validated_data["order"],
            user=request.user,
        )
        return Response(
            CmsNavigationItemSerializer(
                menu.items.filter(parent=parent), many=True,
            ).data
        )


@extend_schema(tags=["CMS Navigation"])
class CmsNavigationPublicView(APIView):
    """``GET /cms/public/navigation/{key}/`` — the resolved menu tree
    for an active menu. 404 for an unknown or inactive key (draft
    isolation)."""

    permission_classes = [permissions.AllowAny]

    @extend_schema(
        responses={
            200: CmsNavigationPublicNodeSerializer(many=True),
            404: None,
        },
    )
    def get(self, request, key):
        menu = CmsNavigationMenu.objects.filter(
            key=key, is_active=True,
        ).first()
        if menu is None:
            return Response(
                {"detail": "Not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        tree = resolve_navigation_tree(menu)
        return Response(
            CmsNavigationPublicNodeSerializer(tree, many=True).data
        )
