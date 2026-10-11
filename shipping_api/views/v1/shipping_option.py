# shipping_api/views/v1/shipping_option.py
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema, OpenApiParameter

from shipping_api.serializers import (
    ShippingOptionSerializer,
    ShippingOptionResponseSerializer,
)
from shipping_api.services import get_shipping_options


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
    responses={200: ShippingOptionResponseSerializer},
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
        except Exception as e:
            error_detail = (
                str(e.detail[0])
                if hasattr(e, "detail")
                and isinstance(e.detail, list)
                else str(e)
            )
            return Response(
                {"detail": error_detail},
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
