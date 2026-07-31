# cart_api/services/cart.py
from django.db import transaction

from rest_framework.exceptions import ValidationError

from cart_api.models import Cart, CartStatus


def get_active_cart(*, user):
    """
    Return the user's active cart.

    Returns None if no active cart exists.
    """
    return Cart.objects.filter(
        created_by=user,
        status=CartStatus.ACTIVE,
        is_active=True,
    ).first()


@transaction.atomic
def get_or_create_active_cart(*, user):
    """
    Return the user's active cart.
    Create one if it does not exist.
    """
    cart = get_active_cart(user=user)

    if cart:
        return cart

    return Cart.objects.create(
        created_by=user,
        updated_by=user,
    )


@transaction.atomic
def checkout_cart(
    *,
    cart,
    user,
):
    """
    Checkout an active cart.

    Business Rules
    --------------
    - Only active carts can be checked out.
    - Empty carts cannot be checked out.
    - A new cart is NOT created here.
      It will be created automatically when the user
      adds a product again.
    """

    if cart.status != CartStatus.ACTIVE:
        raise ValidationError(
            "Only active carts can be checked out."
        )

    if not cart.items.filter(is_active=True).exists():
        raise ValidationError(
            "Cannot checkout an empty cart."
        )

    cart.status = CartStatus.CHECKED_OUT
    cart.updated_by = user

    cart.save(
        update_fields=[
            "status",
            "updated_by",
            "updated_at",
        ]
    )

    return cart


@transaction.atomic
def abandon_cart(
    *,
    cart,
    user,
):
    """
    Abandon an active cart.

    Business Rules
    --------------
    - Only active carts can be abandoned.
    """

    if cart.status != CartStatus.ACTIVE:
        raise ValidationError(
            "Only active carts can be abandoned."
        )

    cart.status = CartStatus.ABANDONED
    cart.updated_by = user

    cart.save(
        update_fields=[
            "status",
            "updated_by",
            "updated_at",
        ]
    )

    return cart
