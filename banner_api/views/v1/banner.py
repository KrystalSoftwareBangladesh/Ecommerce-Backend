# banner_api/views/v1/banner.py
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from banner_api.filters import BannerFilter
from banner_api.models import Banner
from banner_api.serializers import (
    BannerSerializer, BannerStorefrontSerializer, BannerReorderSerializer,
    ReorderBannerResponseSerializer,
)
from banner_api.services.banner import (
    get_available_banners,
    reorder_banners,
)


@extend_schema(tags=["Banners"])
class BannerViewSet(viewsets.ModelViewSet):
    queryset = Banner.objects.select_related("placement").all()
    serializer_class = BannerSerializer

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
    ]
    filterset_class = BannerFilter
    search_fields = ["title", "subtitle"]

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.soft_delete()

        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary="Available banners",
        responses=BannerStorefrontSerializer(many=True),
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="available",
    )
    def available(self, request):
        placement_id = request.query_params.get("placement")

        queryset = get_available_banners(
            placement=placement_id,
        )

        serializer = BannerStorefrontSerializer(
            queryset,
            many=True,
            context=self.get_serializer_context(),
        )

        return Response(serializer.data)

    @extend_schema(
        summary="Reorder banners",
        request=BannerReorderSerializer,
        responses={200: ReorderBannerResponseSerializer},
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="reorder",
    )
    def reorder(self, request):
        serializer = BannerReorderSerializer(
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)

        reorder_banners(
            banner_orders=serializer.validated_data["banners"],
        )

        return Response(
            {"detail": "Banners reordered successfully."}
        )
