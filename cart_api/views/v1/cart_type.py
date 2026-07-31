# cart_api/views/v1/cart_type.py
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from cart_api.models import CartType
from cart_api.serializers import (
    CartTypeCreateUpdateSerializer,
    CartTypeSerializer,
)
from cart_api.services import CartTypeService


class CartTypeViewSet(viewsets.ModelViewSet):
    queryset = CartType.objects.filter(
        is_active=True
    )

    permission_classes = [
        IsAuthenticated,
    ]

    def get_serializer_class(self):
        if self.action in [
            "create",
            "update",
            "partial_update",
        ]:
            return CartTypeCreateUpdateSerializer

        return CartTypeSerializer

    def list(self, request, *args, **kwargs):
        queryset = CartTypeService.list()

        serializer = self.get_serializer(
            queryset,
            many=True,
        )

        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        cart_type = CartTypeService.get(
            self.kwargs["pk"]
        )

        serializer = self.get_serializer(
            cart_type
        )

        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True,
        )

        cart_type = CartTypeService.create(
            **serializer.validated_data,
        )

        return Response(
            CartTypeSerializer(cart_type).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(
        self,
        request,
        *args,
        **kwargs,
    ):
        cart_type = CartTypeService.get(
            self.kwargs["pk"]
        )

        serializer = self.get_serializer(
            cart_type,
            data=request.data,
            partial=True,
        )

        serializer.is_valid(
            raise_exception=True,
        )

        cart_type = CartTypeService.update(
            cart_type,
            **serializer.validated_data,
        )

        return Response(
            CartTypeSerializer(cart_type).data
        )

    def destroy(
        self,
        request,
        *args,
        **kwargs,
    ):
        cart_type = CartTypeService.get(
            self.kwargs["pk"]
        )

        CartTypeService.delete(cart_type)

        return Response(
            status=status.HTTP_204_NO_CONTENT,
        )
