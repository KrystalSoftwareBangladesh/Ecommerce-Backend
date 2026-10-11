# customer_api/views/v1/customer_address.py
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema

from customer_api.models import CustomerAddress
from customer_api import services
from customer_api.serializers import (
    CustomerAddressListSerializer,
    CustomerAddressDetailSerializer,
    CustomerAddressCreateUpdateSerializer,
)


@extend_schema(tags=["Customer Addresses"])
class CustomerAddressViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "patch", "delete", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return CustomerAddress.objects.none()
        customer_profile = services.get_customer_profile(
            self.request.user
        )
        return services.list_addresses(
            customer_profile=customer_profile
        )

    def get_serializer_class(self):
        if self.action == "list":
            return CustomerAddressListSerializer
        if self.action in ("create", "partial_update"):
            return CustomerAddressCreateUpdateSerializer
        return CustomerAddressDetailSerializer

    def perform_create(self, serializer):
        customer_profile = services.get_customer_profile(
            self.request.user
        )
        address = services.create_address(
            customer_profile=customer_profile,
            user=self.request.user,
            validated_data=serializer.validated_data,
        )
        serializer.instance = address

    def perform_update(self, serializer):
        address = services.update_address(
            address=serializer.instance,
            user=self.request.user,
            validated_data=serializer.validated_data,
        )
        serializer.instance = address

    def perform_destroy(self, instance):
        services.delete_address(
            address=instance,
            user=self.request.user,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        read_serializer = CustomerAddressDetailSerializer(
            serializer.instance
        )
        return Response(
            read_serializer.data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(
            instance, data=request.data, partial=partial
        )
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        read_serializer = CustomerAddressDetailSerializer(
            serializer.instance
        )
        return Response(read_serializer.data)
