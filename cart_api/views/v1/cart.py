# cart_api/views/v1/cart.py
from drf_spectacular.utils import extend_schema

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from cart_api.models import Cart
from cart_api.serializers import CartSerializer
from cart_api.services import (
    abandon_cart,
    checkout_cart,
    get_or_create_active_cart,
)


@extend_schema(tags=["Cart"])
class CartViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = CartSerializer
    queryset = Cart.objects.none()
    serializer_class = CartSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses=CartSerializer,
    )
    def retrieve(self, request, *args, **kwargs):
        cart = get_or_create_active_cart(
            user=request.user,
            with_summary=True,
        )

        serializer = self.get_serializer(cart)

        return Response(serializer.data)

    @extend_schema(
        responses=CartSerializer,
    )
    @action(
        detail=False,
        methods=["get"],
    )
    def active(self, request):
        cart = get_or_create_active_cart(
            user=request.user,
            with_summary=True,
        )

        serializer = self.get_serializer(cart)

        return Response(serializer.data)

    @extend_schema(
        request=None,
        responses={200: None},
        description="Checkout active cart.",
    )
    @action(
        detail=False,
        methods=["post"],
    )
    def checkout(self, request):
        cart = get_or_create_active_cart(
            user=request.user,
        )

        checkout_cart(
            cart=cart,
            user=request.user,
        )

        return Response(
            {
                "detail": "Cart checked out successfully."
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        request=None,
        responses={200: None},
        description="Abandon active cart.",
    )
    @action(
        detail=False,
        methods=["post"],
    )
    def abandon(self, request):
        cart = get_or_create_active_cart(
            user=request.user,
        )

        abandon_cart(
            cart=cart,
            user=request.user,
        )

        return Response(
            {
                "detail": "Cart abandoned successfully."
            },
            status=status.HTTP_200_OK,
        )
