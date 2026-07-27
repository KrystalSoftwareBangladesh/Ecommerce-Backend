# wishlist_api/views/v1/wishlist.py
from rest_framework import mixins, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from drf_spectacular.utils import extend_schema

from wishlist_api.models import Wishlist
from wishlist_api.serializers import (
    WishlistCreateSerializer,
    WishlistListSerializer,
)
from wishlist_api.services import (
    create_wishlist,
    remove_wishlist,
)


@extend_schema(tags=["Wishlists"])
class WishlistViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Wishlist.objects.filter(
                created_by=self.request.user,
                is_active=True,
            )
            .select_related("product")
            .order_by("-created_at", "id")
        )

    def get_serializer_class(self):
        if self.action == "create":
            return WishlistCreateSerializer

        return WishlistListSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product = serializer.validated_data["product"]

        wishlist = create_wishlist(
            user=request.user,
            product=product,
        )

        return Response(
            WishlistListSerializer(
                wishlist,
                context=self.get_serializer_context(),
            ).data,
            status=status.HTTP_201_CREATED,
        )

    def destroy(self, request, *args, **kwargs):
        wishlist = self.get_object()

        remove_wishlist(wishlist=wishlist)

        return Response(status=status.HTTP_204_NO_CONTENT)
