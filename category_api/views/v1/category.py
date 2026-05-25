# category_api/views/category.py
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema

from rest_framework import viewsets
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
        "id",
    ]

    ordering = ["name", "id"]

    def get_queryset(self):
        qs = super().get_queryset()
        return qs
