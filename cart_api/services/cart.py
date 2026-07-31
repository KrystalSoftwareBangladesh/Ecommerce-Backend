# cart_api/services/cart.py
from django.db import transaction
from django.db.models import (
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    Q,
    Sum,
)
from django.db.models.functions import Coalesce

from rest_framework.exceptions import ValidationError

from EcommerceBackend.core.choices import CartStatus
from cart_api.models import Cart


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


# @transaction.atomic
# def get_or_create_active_cart(*, user):
#     """
#     Return the user's active cart.
#     Create one if it does not exist.
#     """
#     cart = get_active_cart(user=user)

#     if cart:
#         return cart

#     return Cart.objects.create(
#         created_by=user,
#         updated_by=user,
#     )
@transaction.atomic
def get_or_create_active_cart(
    *,
    user,
    with_summary: bool = False,
):
    """
    Return the user's active cart.
    Create one if it does not exist.

    If `with_summary` is True, annotate the cart with:
    - total_items
    - total_quantity
    - subtotal
    """
    cart = get_active_cart(user=user)

    if cart is None:
        cart = Cart.objects.create(
            created_by=user,
            updated_by=user,
        )

    if not with_summary:
        return cart

    return (
        Cart.objects.filter(pk=cart.pk)
        .annotate(
            total_items=Count(
                "items",
                filter=Q(items__is_active=True),
            ),
            total_quantity=Coalesce(
                Sum(
                    "items__quantity",
                    filter=Q(items__is_active=True),
                ),
                0,
            ),
            subtotal=Coalesce(
                Sum(
                    ExpressionWrapper(
                        F("items__quantity")
                        * F("items__product__current_selling_price"),
                        output_field=DecimalField(
                            max_digits=12,
                            decimal_places=2,
                        ),
                    ),
                    filter=Q(items__is_active=True),
                ),
                0,
            ),
        )
        .first()
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
