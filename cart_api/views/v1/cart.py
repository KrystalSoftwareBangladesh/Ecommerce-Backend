# cart_api/views/v1/cart.py
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from drf_spectacular.utils import extend_schema

from cart_api.models import Cart
from cart_api.serializers import (
    CartCreateUpdateSerializer,
    CartListSerializer,
)
from cart_api.services import (
    add_to_cart,
    remove_cart_item,
    update_cart_item,
)


@extend_schema(tags=["Carts"])
class CartViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]

    http_method_names = [
        "get",
        "post",
        "patch",
        "delete",
    ]

    def get_queryset(self):
        return (
            Cart.objects.filter(
                created_by=self.request.user,
                is_active=True,
            )
            .select_related("product")
            .order_by("-created_at", "id")
        )

    def get_serializer_class(self):
        if self.action in (
            "create",
            "partial_update",
        ):
            return CartCreateUpdateSerializer

        return CartListSerializer

    def retrieve(self, request, *args, **kwargs):
        return Response(
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cart = add_to_cart(
            user=request.user,
            product=serializer.validated_data["product"],
            quantity=serializer.validated_data["quantity"],
        )

        return Response(
            CartListSerializer(
                cart,
                context=self.get_serializer_context(),
            ).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, *args, **kwargs):
        cart = self.get_object()

        serializer = self.get_serializer(
            cart,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)

        cart = update_cart_item(
            cart=cart,
            quantity=serializer.validated_data["quantity"],
        )

        return Response(
            CartListSerializer(
                cart,
                context=self.get_serializer_context(),
            ).data
        )

    def destroy(self, request, *args, **kwargs):
        cart = self.get_object()

        remove_cart_item(cart=cart)

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )
