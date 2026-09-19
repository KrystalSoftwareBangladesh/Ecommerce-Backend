# banner_api/views/v1/banner.py
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from banner_api.filters import BannerFilter
from banner_api.models import Banner
from banner_api.serializers import (
    BannerSerializer,
    BannerStorefrontSerializer,
)
from banner_api.services.banner import (
    get_available_banners,
    reorder_banners,
)


class BannerViewSet(ModelViewSet):
    queryset = Banner.objects.select_related("placement").all()
    serializer_class = BannerSerializer

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]
    filterset_class = BannerFilter

    search_fields = [
        "title",
        "subtitle",
    ]

    ordering_fields = [
        "display_order",
        "created_at",
        "updated_at",
        "start_at",
        "end_at",
    ]
    ordering = ["display_order", "-created_at"]

    @action(
        detail=False,
        methods=["get"],
        url_path="available",
        serializer_class=BannerStorefrontSerializer,
    )
    def available(self, request):
        placement_id = request.query_params.get("placement")

        banners = get_available_banners(
            placement=placement_id,
        )

        serializer = self.get_serializer(banners, many=True)

        return Response(serializer.data)

    @action(
        detail=False,
        methods=["post"],
        url_path="reorder",
    )
    def reorder(self, request):
        banner_orders = request.data.get("banners")

        if not isinstance(banner_orders, list):
            return Response(
                {"detail": "banners must be a list."},
                status=400,
            )

        reorder_banners(
            banner_orders=banner_orders,
        )

        return Response(
            {"detail": "Banners reordered successfully."}
        )
