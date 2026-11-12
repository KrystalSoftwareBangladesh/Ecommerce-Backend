# cms_api/views/v1/cms_preview.py
"""Public, token-gated preview resolution (docs/cms-architecture.md
§5.7, §6, AD-15).

``AllowAny`` per spec §6: the signed token itself carries the user
and permission binding, re-checked on every resolve.
"""
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from cms_api.serializers import (
    CmsPagePreviewSerializer,
    CmsSectionPreviewSerializer,
)
from cms_api.services.preview import KIND_PAGE, resolve_preview_token


@extend_schema(tags=["CMS"])
class CmsPreviewView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        responses={
            200: CmsPagePreviewSerializer,
        },
    )
    def get(self, request, token):
        kind, obj, revision = resolve_preview_token(token=token)
        serializer_class = (
            CmsPagePreviewSerializer
            if kind == KIND_PAGE
            else CmsSectionPreviewSerializer
        )
        response = Response(serializer_class(obj).data)
        response["Cache-Control"] = "no-store"
        return response
