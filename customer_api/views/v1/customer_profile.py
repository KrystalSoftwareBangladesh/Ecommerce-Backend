from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from drf_spectacular.utils import extend_schema

from customer_api.models import CustomerProfile
from customer_api.serializers import (
    CustomerProfileCreateSerializer,
    CustomerProfileUpdateSerializer,
    CustomerProfileListSerializer,
    CustomerProfileDetailSerializer,
)


class CustomerProfilePermission(IsAuthenticated):
    def has_permission(self, request, view):
        # Only owner (superuser) can create new customers
        if view.action == "create":
            return request.user.is_superuser
        return True

    def has_object_permission(self, request, view, obj):
        # Owner full access
        if request.user.is_superuser:
            return True
        # Customer can only touch their own profile (except delete)
        if view.action in ["retrieve", "update", "partial_update"]:
            return obj.user == request.user
        # Delete (soft) only by owner
        if view.action == "destroy":
            return request.user.is_superuser
        return False


@extend_schema(tags=["Customers"])
class CustomerViewSet(viewsets.ModelViewSet):
    queryset = CustomerProfile.objects.select_related("user").all()
    permission_classes = [CustomerProfilePermission]
    filter_backends = [DjangoFilterBackend,
                       filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["customer_type", "is_active"]
    search_fields = [
        "user__first_name", "user__middle_name", "user__last_name",
        "user__email", "phone", "facebook_profile_url",
    ]
    ordering_fields = ["created_at", "user__first_name", "id"]
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        qs = super().get_queryset()
        # Customers see only their own profile
        if not self.request.user.is_superuser:
            qs = qs.filter(user=self.request.user)
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return CustomerProfileCreateSerializer
        if self.action in ["update", "partial_update"]:
            return CustomerProfileUpdateSerializer
        if self.action == "list":
            return CustomerProfileListSerializer
        return CustomerProfileDetailSerializer

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save()
