# cart_api/views/cart_item.py
from django_filters.rest_framework import DjangoFilterBackend

from drf_spectacular.utils import extend_schema

from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from cart_api.models import CartItem
from cart_api.serializers import (
    CartItemSerializer,
    CartItemCreateUpdateSerializer,
)
from cart_api.services import (
    list_cart_items,
)


@extend_schema(tags=["Cart"])
class CartItemViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]

    filter_backends = [
        DjangoFilterBackend,
    ]

    queryset = CartItem.objects.none()

    def get_queryset(self):
        return list_cart_items(
            user=self.request.user,
        )

    def get_serializer_class(self):
        if self.action == "list":
            return CartItemSerializer

        return CartItemCreateUpdateSerializer
