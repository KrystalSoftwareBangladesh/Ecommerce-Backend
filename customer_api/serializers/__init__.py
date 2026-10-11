# customer_api/serializers/__init__.py
from .customer_profile import (
    CustomerProfileCreateSerializer,
    CustomerProfileDetailSerializer,
    CustomerProfileListSerializer,
    CustomerProfileUpdateSerializer,
)
from .customer_address import (
    CustomerAddressListSerializer,
    CustomerAddressDetailSerializer,
    CustomerAddressCreateUpdateSerializer,
)


__all__ = [
    "CustomerProfileCreateSerializer",
    "CustomerProfileDetailSerializer",
    "CustomerProfileListSerializer",
    "CustomerProfileUpdateSerializer",
    "CustomerAddressListSerializer",
    "CustomerAddressDetailSerializer",
    "CustomerAddressCreateUpdateSerializer",
]
