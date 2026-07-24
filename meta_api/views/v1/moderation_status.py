# meta_api/views/v1/moderation_status.py
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema

from meta_api.serializers import ModerationStatusChoiceSerializer
from meta_api.services import get_moderation_statuses


@extend_schema(
    tags=["Meta"],
    responses={200: ModerationStatusChoiceSerializer(many=True)},
)
class ModerationStatusListAPIView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response(
            get_moderation_statuses(),
            status=status.HTTP_200_OK,
        )
