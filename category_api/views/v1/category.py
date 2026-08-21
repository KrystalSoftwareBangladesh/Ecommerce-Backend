# category_api/views/category.py
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
)
from django.db import transaction
from django.db.models import Prefetch, Exists, OuterRef, Count, Q, F

from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.exceptions import ValidationError

from EcommerceBackend.core.permission import PublicReadPermissionMixin

from category_api.models import Category
from category_api.serializers import (
    CategorySerializer, CategoryDetailsSerializer, CategoryListSerializer,
    CategoryNavigationSerializer, CategoryStatisticsSerializer,
    CategoryBulkMenuUpdateSerializer, CategoryBulkMenuUpdateResponseSerializer,
)
from category_api.filters import CategoryFilter


@extend_schema(tags=["Categories"])
class CategoryViewSet(PublicReadPermissionMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    public_actions = PublicReadPermissionMixin.public_actions + [
        "roots",
        "children",
    ]
    serializer_class = CategorySerializer
    queryset = Category.objects.filter(
        deleted_at__isnull=True
    )

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    filterset_class = CategoryFilter
    lookup_field = "slug"

    search_fields = [
        "name",
        "description",
    ]
    ordering_fields = [
        "display_order",
        "name",
    ]
    ordering = ["display_order", "name"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "retrieve":
            children_qs = Category.objects.filter(
                deleted_at__isnull=True
            )

            return qs.prefetch_related(
                Prefetch(
                    "subcategories",
                    queryset=children_qs,
                )
            )

        return qs

    def get_serializer_class(self):
        if self.action == "list":
            return CategoryListSerializer
        if self.action == "retrieve":
            return CategoryDetailsSerializer

        return CategorySerializer

    def _get_category_ids_from_params(self, queryset):
        ids = self.request.query_params.get("ids")
        slugs = self.request.query_params.get("slugs")

        category_ids = set()

        if ids:
            try:
                category_ids.update(
                    int(value.strip())
                    for value in ids.split(",")
                    if value.strip()
                )
            except ValueError:
                raise ValidationError({
                    "ids": "IDs must be comma-separated integers."
                })

        if slugs:
            slug_values = [
                value.strip()
                for value in slugs.split(",")
                if value.strip()
            ]

            category_ids.update(
                queryset.filter(
                    slug__in=slug_values
                ).values_list("id", flat=True)
            )

        return category_ids

    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def _set_show_in_menu(self, category, show_in_menu):
        if category.show_in_menu != show_in_menu:
            category.show_in_menu = show_in_menu
            category.updated_by = self.request.user

            category.save(update_fields=[
                "show_in_menu",
                "updated_by",
                "updated_at",
            ])

        serializer = CategoryDetailsSerializer(
            category,
            context=self.get_serializer_context(),
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["Categories"],
        request=None,
        responses={200: CategoryDetailsSerializer},
        description="Mark a category to be shown in the navigation menu.",
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="mark-as-menu",
    )
    def mark_as_menu(self, request, slug=None):
        return self._set_show_in_menu(self.get_object(), True)

    @extend_schema(
        tags=["Categories"],
        request=None,
        responses={200: CategoryDetailsSerializer},
        description="Remove a category from the navigation menu.",
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="remove-from-menu",
    )
    def remove_from_menu(self, request, slug=None):
        return self._set_show_in_menu(self.get_object(), False)

    @extend_schema(
        tags=["Categories"],
        summary="Category summary",
        filters=False,
        responses={200: CategoryStatisticsSerializer},
        description=(
            "Category counts grouped by hierarchy and menu visibility."
        ),
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="summary",
    )
    def summary(self, request):
        statistics = Category.objects.filter(
            deleted_at__isnull=True,
        ).aggregate(
            total_categories=Count("id"),
            root_categories=Count(
                "id",
                filter=Q(parent__isnull=True),
            ),
            sub_categories=Count(
                "id",
                filter=Q(parent__isnull=False),
            ),
            menu_categories=Count(
                "id",
                filter=Q(show_in_menu=True, parent__isnull=True),
            ),
            sub_menu_categories=Count(
                "id",
                filter=Q(show_in_menu=True, parent__isnull=False),
            ),
        )

        serializer = CategoryStatisticsSerializer(statistics)

        return Response(serializer.data)

    @extend_schema(
        tags=["Categories"],
        parameters=[
            OpenApiParameter(
                name="ids",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Comma-separated category IDs.",
            ),
            OpenApiParameter(
                name="slugs",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Comma-separated category slugs.",
            ),
            OpenApiParameter(
                name="is_menu",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter categories by storefront menu visibility.",
            ),
        ],
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="roots",
    )
    def roots(self, request):
        children_exists = Category.objects.filter(
            parent_id=OuterRef("pk"),
            deleted_at__isnull=True,
        )

        queryset = Category.objects.filter(
            deleted_at__isnull=True,
            parent__isnull=True,
        ).annotate(
            has_children=Exists(children_exists)
        )

        ids = request.query_params.get("ids")
        slugs = request.query_params.get("slugs")
        if ids or slugs:
            category_ids = self._get_category_ids_from_params(queryset)
            queryset = queryset.filter(id__in=category_ids)

        is_menu = request.query_params.get("is_menu")
        if is_menu == "true":
            queryset = queryset.filter(show_in_menu=True)
        elif is_menu == "false":
            queryset = queryset.filter(show_in_menu=False)

        queryset = queryset.order_by(
            "display_order",
            "name",
            "id",
        )

        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = CategoryNavigationSerializer(
                page,
                many=True,
                context=self.get_serializer_context(),
            )
            return self.get_paginated_response(serializer.data)

        serializer = CategoryNavigationSerializer(
            queryset,
            many=True,
            context=self.get_serializer_context(),
        )

        return Response(serializer.data)

    @extend_schema(
        tags=["Categories"],
        parameters=[
            OpenApiParameter(
                name="ids",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Comma-separated parent category IDs.",
            ),
            OpenApiParameter(
                name="slugs",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Comma-separated parent category slugs.",
            ),
            OpenApiParameter(
                name="is_menu",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter categories by storefront menu visibility.",
            ),
        ],
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="children",
    )
    def children(self, request):
        parent_queryset = Category.objects.filter(
            deleted_at__isnull=True,
        )

        parent_ids = self._get_category_ids_from_params(
            parent_queryset
        )

        if not parent_ids:
            raise ValidationError({
                "detail": "At least one category ID or slug is required."
            })

        children_exists = Category.objects.filter(
            parent_id=OuterRef("pk"),
            deleted_at__isnull=True,
        )

        queryset = Category.objects.filter(
            deleted_at__isnull=True,
            parent_id__in=parent_ids,
        ).annotate(
            has_children=Exists(children_exists)
        ).order_by(
            "parent_id",
            "display_order",
            "name",
            "id",
        )

        is_menu = request.query_params.get("is_menu")
        if is_menu == "true":
            queryset = queryset.filter(show_in_menu=True)
        elif is_menu == "false":
            queryset = queryset.filter(show_in_menu=False)

        serializer = CategoryNavigationSerializer(
            queryset,
            many=True,
            context=self.get_serializer_context(),
        )

        return Response(serializer.data)

    def _apply_bulk_filters(self, queryset, filters):
        is_parent = filters.get("is_parent")
        is_menu = filters.get("is_menu")
        is_active = filters.get("is_active")
        search = filters.get("search")

        if is_parent is True:
            queryset = queryset.filter(parent__isnull=True)
        elif is_parent is False:
            queryset = queryset.filter(parent__isnull=False)

        if is_menu is True:
            queryset = queryset.filter(show_in_menu=True)
        elif is_menu is False:
            queryset = queryset.filter(show_in_menu=False)

        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(description__icontains=search)
            )

        return queryset

    @extend_schema(
        tags=["Categories"],
        request=CategoryBulkMenuUpdateSerializer,
        responses={
            200: CategoryBulkMenuUpdateResponseSerializer,
        },
        description=(
            "Bulk update storefront menu visibility for multiple categories. "
            "Categories can be identified by IDs, slugs, or both."
        ),
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="bulk-menu-update",
    )
    def bulk_menu_update(self, request):
        serializer = CategoryBulkMenuUpdateSerializer(
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)

        ids = serializer.validated_data.get("ids", [])
        slugs = serializer.validated_data.get("slugs", [])
        select_all = serializer.validated_data.get("select_all", False)
        filters = serializer.validated_data.get("filters", {})
        show_in_menu = serializer.validated_data["show_in_menu"]

        queryset = Category.objects.filter(
            deleted_at__isnull=True,
        )

        if select_all:
            # Update all categories matching the provided filters.
            queryset = self._apply_bulk_filters(
                queryset,
                filters,
            )
        else:
            # Update only explicitly selected categories.
            selection_filter = Q()
            if ids:
                selection_filter |= Q(id__in=ids)
            if slugs:
                selection_filter |= Q(slug__in=slugs)

            queryset = queryset.filter(selection_filter)

        updated_count = queryset.update(
            show_in_menu=show_in_menu,
            updated_by=request.user,
        )

        response_data = {
            "updated_count": updated_count,
            "show_in_menu": show_in_menu,
        }

        return Response(
            CategoryBulkMenuUpdateResponseSerializer(
                response_data,
            ).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["Categories"],
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "display_order": {
                        "type": "integer",
                        "minimum": 1,
                    },
                },
                "required": ["display_order"],
            }
        },
        responses={200: CategoryDetailsSerializer},
        description="Update the display order of a category.",
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="reorder",
    )
    def reorder(self, request, slug=None):
        category = self.get_object()

        try:
            new_order = int(request.data.get("display_order"))
        except (TypeError, ValueError):
            raise ValidationError({
                "display_order": "Display order must be an integer."
            })

        if new_order < 1:
            raise ValidationError({
                "display_order": "Display order must be greater than 0."
            })

        with transaction.atomic():
            siblings = Category.objects.filter(
                deleted_at__isnull=True,
                parent_id=category.parent_id,
            )

            sibling_count = siblings.exclude(
                pk=category.pk,
            ).count() + 1

            if new_order > sibling_count:
                new_order = sibling_count

            current_order = category.display_order

            if current_order == new_order:
                return Response(
                    CategoryDetailsSerializer(
                        category,
                        context=self.get_serializer_context(),
                    ).data,
                    status=status.HTTP_200_OK,
                )

            if new_order < current_order:
                siblings.filter(
                    display_order__gte=new_order,
                    display_order__lt=current_order,
                ).update(
                    display_order=F("display_order") + 1,
                )

            else:
                siblings.filter(
                    display_order__gt=current_order,
                    display_order__lte=new_order,
                ).update(
                    display_order=F("display_order") - 1,
                )

            category.display_order = new_order
            category.updated_by = request.user

            category.save(
                update_fields=[
                    "display_order",
                    "updated_by",
                    "updated_at",
                ]
            )

        return Response(
            CategoryDetailsSerializer(
                category,
                context=self.get_serializer_context(),
            ).data,
            status=status.HTTP_200_OK,
        )
