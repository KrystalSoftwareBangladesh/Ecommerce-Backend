# customer_api/serializers/__init__.py
from .customer_profile import (
    CustomerProfileCreateSerializer,
    CustomerProfileDetailSerializer,
    CustomerProfileListSerializer,
    CustomerProfileUpdateSerializer,
)


__all__ = [
    "CustomerProfileCreateSerializer",
    "CustomerProfileDetailSerializer",
    "CustomerProfileListSerializer",
    "CustomerProfileUpdateSerializer",
]
