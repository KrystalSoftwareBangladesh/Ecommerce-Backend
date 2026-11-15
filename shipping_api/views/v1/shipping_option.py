# shipping_api/views/v1/shipping_option.py
import logging
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema, OpenApiParameter

from shipping_api.serializers import (
    ShippingOptionSerializer,
)
from shipping_api.services import get_shipping_options

logger = logging.getLogger(__name__)


@extend_schema(
    tags=["Shipping Options"],
    parameters=[
        OpenApiParameter(
            name="address_id",
            type=int,
            required=True,
            description=(
                "ID of the customer's shipping address."
            ),
        ),
    ],
    responses={200: ShippingOptionSerializer(many=True)},
)
class ShippingOptionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        address_id = request.query_params.get(
            "address_id"
        )

        if not address_id:
            return Response(
                {
                    "detail": (
                        "address_id query parameter "
                        "is required."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            address_id = int(address_id)
        except (TypeError, ValueError):
            return Response(
                {"detail": "address_id must be an integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = get_shipping_options(
                user=request.user,
                address_id=address_id,
            )
        except Exception:
            logger.exception(
                "Failed to get shipping options for user_id=%s address_id=%s",
                request.user.id,
                address_id,
            )
            return Response(
                {
                    "detail": (
                        "Unable to retrieve shipping options "
                        "at this time."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ShippingOptionSerializer(
            result["options"], many=True
        )

        return Response(
            {
                "zone": {
                    "id": result["zone"].id,
                    "name": result["zone"].name,
                    "code": result["zone"].code,
                },
                "cart_subtotal": (
                    result["cart_subtotal"]
                ),
                "options": serializer.data,
            }
        )
