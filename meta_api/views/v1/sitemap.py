# meta_api/views/v1/sitemap.py
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema

from meta_api.serializers import SitemapUrlsSerializer
from meta_api.services import get_sitemap_urls


@extend_schema(
    tags=["SEO"],
    responses={200: SitemapUrlsSerializer},
)
class SitemapUrlsAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        serializer = SitemapUrlsSerializer(get_sitemap_urls())

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )
