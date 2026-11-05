# customer_api/services/customer_address.py
from django.db import transaction

from rest_framework.exceptions import ValidationError

from customer_api.models import CustomerProfile, CustomerAddress


def get_customer_profile(user):
    """Return the CustomerProfile for the given user or None."""
    try:
        return user.customer_profile
    except CustomerProfile.DoesNotExist:
        return None


def get_or_create_customer_profile(user):
    """Return the user's profile, provisioning one if absent.

    An inactive profile raises instead of being reactivated or
    replaced.
    """
    profile, _ = CustomerProfile.objects.get_or_create(
        user=user,
        defaults={"customer_type": "WEBSITE"},
    )
    if not profile.is_active:
        raise ValidationError(
            "Customer profile is inactive for this user."
        )
    return profile


def list_addresses(*, customer_profile):
    """Return all active, non-deleted addresses for a customer."""
    return CustomerAddress.objects.filter(
        customer=customer_profile,
        is_active=True,
        deleted_at__isnull=True,
    ).select_related("shipping_zone")


def create_address(*, user, validated_data):
    """Create an address, provisioning the profile if needed."""
    with transaction.atomic():
        customer_profile = get_or_create_customer_profile(user)
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
