# customer_api/models/__init__.py
from .customer import CustomerProfile
from .customer_address import CustomerAddress


__all__ = [
    "CustomerProfile",
    "CustomerAddress",
]
