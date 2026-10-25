# customer_api/services/customer_address.py
from django.core.exceptions import ValidationError
from django.db import transaction

from customer_api.models import CustomerAddress


def get_customer_profile(user):
    """Return the CustomerProfile for the given user or raise."""
    try:
        return user.customer_profile
    except Exception:
        raise ValidationError(
            "No customer profile found for this user."
        )


def list_addresses(*, customer_profile):
    """Return all active, non-deleted addresses for a customer."""
    return CustomerAddress.objects.filter(
        customer=customer_profile,
        is_active=True,
        deleted_at__isnull=True,
    ).select_related("shipping_zone")


def create_address(*, customer_profile, user, validated_data):
    """Create a new address for the given customer profile."""
    with transaction.atomic():
        address = CustomerAddress.objects.create(
            customer=customer_profile,
            created_by=user,
            updated_by=user,
            **validated_data,
        )
    return address


def update_address(*, address, user, validated_data):
    """Update an existing address."""
    with transaction.atomic():
        for field, value in validated_data.items():
            setattr(address, field, value)
        address.updated_by = user
        address.save()
    return address


def delete_address(*, address, user):
    """Soft-delete an address."""
    address.updated_by = user
    address.save(update_fields=["updated_by", "updated_at"])
    address.soft_delete()
    return address
