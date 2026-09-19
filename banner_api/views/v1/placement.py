# banner_api/views/v1/placement.py
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.viewsets import ModelViewSet

from banner_api.filters import BannerPlacementFilter
from banner_api.models import BannerPlacement
from banner_api.serializers import BannerPlacementSerializer


class BannerPlacementViewSet(ModelViewSet):
    queryset = BannerPlacement.objects.all()
    serializer_class = BannerPlacementSerializer

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]
    filterset_class = BannerPlacementFilter
    search_fields = ["name", "code"]
    ordering_fields = ["name", "code", "created_at", "updated_at"]
    ordering = ["name"]
