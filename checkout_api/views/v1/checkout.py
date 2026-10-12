# checkout_api/views/v1/checkout.py
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema

from checkout_api.serializers import (
    CheckoutValidateSerializer,
    CheckoutValidateResponseSerializer,
)
from checkout_api.services import validate_checkout


@extend_schema(
    tags=["Checkout"],
    request=CheckoutValidateSerializer,
    responses={
        200: CheckoutValidateResponseSerializer,
    },
)
class CheckoutValidateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CheckoutValidateSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        result = validate_checkout(
            user=request.user,
            shipping_address_id=(
                serializer.validated_data[
                    "shipping_address_id"
                ]
            ),
            shipping_method_id=(
                serializer.validated_data[
                    "shipping_method_id"
                ]
            ),
        )

        return Response(
            result,
            status=status.HTTP_200_OK,
        )
