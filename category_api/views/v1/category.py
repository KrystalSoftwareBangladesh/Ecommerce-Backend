# category_api/views/category.py
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from django.db.models import Prefetch

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter

from EcommerceBackend.core.permission import PublicListPermissionMixin

from category_api.models import Category
from category_api.serializers import CategorySerializer
from category_api.filters import CategoryFilter


@extend_schema(tags=["Categories"])
class CategoryViewSet(PublicListPermissionMixin, viewsets.ModelViewSet):
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

    def get_queryset(self):
        qs = super().get_queryset()
        # Prefetch subcategories to avoid N+1 queries
        children_qs = Category.objects.filter(deleted_at__isnull=True)
        qs = qs.prefetch_related(
            Prefetch('subcategories', queryset=children_qs)
        )
        return qs

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
