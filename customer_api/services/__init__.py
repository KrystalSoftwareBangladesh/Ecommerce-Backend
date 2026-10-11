# customer_api/services/__init__.py
from .customer_address import (  # noqa: F401
    get_customer_profile,
    list_addresses,
    create_address,
    update_address,
    delete_address,
)
