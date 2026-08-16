# category_api/views/category.py
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
)
from django.db.models import Prefetch, Exists, OuterRef, Count, Q

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
    CategoryTreeListSerializer, CategoryNavigationSerializer,
    CategoryStatisticsSerializer,
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
        "name",
        "created_at",
        "order",
        "id",
    ]

    ordering = ["order", "name", "id"]

    # def get_queryset(self):
    #     qs = super().get_queryset()
    #     # Prefetch subcategories to avoid N+1 queries
    #     children_qs = Category.objects.filter(deleted_at__isnull=True)
    #     qs = qs.prefetch_related(
    #         Prefetch('subcategories', queryset=children_qs)
    #     )
    #     return qs
    # def get_queryset(self):
    #     qs = super().get_queryset()

    #     if (
    #         self.action == "list"
    #         and self.request.query_params.get("is_parent") == "true"
    #     ):
    #         return qs

    #     children_qs = Category.objects.filter(
    #         deleted_at__isnull=True
    #     )

    #     return qs.prefetch_related(
    #         Prefetch(
    #             "subcategories",
    #             queryset=children_qs,
    #         )
    #     )
    def get_queryset(self):
        qs = super().get_queryset()

        if self.action in [
            "roots",
            "children",
            "mark_as_menu",
            "remove_from_menu",
        ]:
            return qs

        if (
            self.action == "list"
            and self.request.query_params.get("is_parent") == "true"
        ):
            return qs

        children_qs = Category.objects.filter(
            deleted_at__isnull=True
        )

        return qs.prefetch_related(
            Prefetch(
                "subcategories",
                queryset=children_qs,
            )
        )

    def get_serializer_class(self):
        if self.action == "list":
            return CategoryListSerializer
        if self.action == "retrieve":
            return CategoryDetailsSerializer

        return CategorySerializer

    def _build_category_tree(self, roots):
        """
        Build the complete category hierarchy in memory for the parent-category
        tree endpoint, avoiding recursive database queries during
        serialization.
        """
        categories = list(
            Category.objects.filter(
                deleted_at__isnull=True,
            ).only(
                "id",
                "slug",
                "name",
                "parent_id",
                "order",
                "show_in_menu",
            )
        )

        children_map = {}

        for category in categories:
            children_map.setdefault(category.parent_id, []).append(category)

        for children in children_map.values():
            children.sort(
                key=lambda category: (
                    category.order,
                    category.name,
                    category.id,
                )
            )

        def attach_children(category):
            children = children_map.get(category.id, [])
            category._tree_children = children

            for child in children:
                attach_children(child)

        for root in roots:
            attach_children(root)

        return roots

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
        if request.query_params.get("is_parent") != "true":
            return super().list(request, *args, **kwargs)

        # The parent-category endpoint returns the complete nested hierarchy.
        # Build the tree in memory to avoid recursive N+1 queries.
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)

        if page is not None:
            roots = list(page)
        else:
            roots = list(queryset)

        roots = self._build_category_tree(roots)

        serializer = CategoryTreeListSerializer(
            roots,
            many=True,
            context=self.get_serializer_context(),
        )

        if page is not None:
            return self.get_paginated_response(serializer.data)

        return Response(serializer.data)

    @extend_schema(tags=["Categories"])
    @action(detail=False, methods=['post'], url_path='edit-by-slug')
    def edit_by_slug(self, request):
        """
        Edit a category by slug.
        Expected payload: {
            "slug": "category-slug",
            "name": "New Name",
            "description": "New description",
            ...
        }
        """
        slug = request.data.get('slug')

        if not slug:
            return Response(
                {'error': 'slug is required in payload'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            category = Category.objects.get(
                slug=slug,
                deleted_at__isnull=True
            )
        except Category.DoesNotExist:
            error_msg = f'Category with slug "{slug}" not found'
            return Response(
                {'error': error_msg},
                status=status.HTTP_404_NOT_FOUND
            )

        # Create a copy of request data without the slug for
        # serializer validation
        update_data = request.data.copy()
        # Remove slug from update data to avoid validation issues
        update_data.pop('slug', None)

        serializer = self.get_serializer(
            category,
            data=update_data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response(
                serializer.data,
                status=status.HTTP_200_OK
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

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
        ],
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="roots",
    )
    def roots(self, request):
        # queryset = Category.objects.filter(
        #     deleted_at__isnull=True,
        #     parent__isnull=True,
        # )
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

        queryset = queryset.order_by(
            "order",
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
        ],
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="children",
    )
    def children(self, request):
        # parent_queryset = Category.objects.filter(
        #     deleted_at__isnull=True,
        # )

        # parent_ids = self._get_category_ids_from_params(
        #     parent_queryset
        # )

        # if not parent_ids:
        #     raise ValidationError({
        #         "detail": "At least one category ID or slug is required."
        #     })

        # queryset = Category.objects.filter(
        #     deleted_at__isnull=True,
        #     parent_id__in=parent_ids,
        # ).order_by(
        #     "parent_id",
        #     "order",
        #     "name",
        #     "id",
        # )
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
            "order",
            "name",
            "id",
        )

        serializer = CategoryNavigationSerializer(
            queryset,
            many=True,
            context=self.get_serializer_context(),
        )

        return Response(serializer.data)
