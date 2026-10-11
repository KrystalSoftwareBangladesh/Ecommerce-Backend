# customer_api/views/v1/__init__.py
from .customer_profile import (
    CustomerViewSet,
)
from .customer_address import (
    CustomerAddressViewSet,
)


__all__ = [
    "CustomerViewSet",
    "CustomerAddressViewSet",
]
