# banner_api/views/v1/placement.py
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, filters


from EcommerceBackend.core.permission import (
    PublicReadPermissionMixin,
)
from banner_api.filters import BannerPlacementFilter
from banner_api.models import BannerPlacement
from banner_api.serializers import BannerPlacementSerializer


class BannerPlacementViewSet(PublicReadPermissionMixin, viewsets.ModelViewSet):
    queryset = BannerPlacement.objects.all()
    serializer_class = BannerPlacementSerializer

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
    ]
    filterset_class = BannerPlacementFilter
    search_fields = ["name", "code"]
