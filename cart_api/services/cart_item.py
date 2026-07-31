# cart_api/services/cart_item.py
from django.db import transaction

from rest_framework.exceptions import ValidationError

from EcommerceBackend.core.choices import CartStatus
from cart_api.models import CartItem
from cart_api.services.cart import get_or_create_active_cart


def list_cart_items(*, user):
    """
    Return all active items from the user's active cart.
    """
    cart = get_or_create_active_cart(user=user)

    return (
        cart.items.filter(is_active=True)
        .select_related("product")
        .order_by("created_at")
    )


@transaction.atomic
def add_cart_item(
    *,
    user,
    product,
    quantity,
):
    """
    Add a product into the user's active cart.

    Business Rules
    --------------
    - Create an active cart if none exists.
    - If the product already exists, increase quantity.
    - Otherwise create a new cart item.
    """

    if quantity < 1:
        raise ValidationError(
            "Quantity must be greater than zero."
        )

    cart = get_or_create_active_cart(user=user)

    cart_item = cart.items.filter(
        product=product,
        is_active=True,
    ).first()

    if cart_item:
        cart_item.quantity += quantity

        cart_item.save(
            update_fields=[
                "quantity",
                "updated_at",
            ]
        )

        return cart_item

    return CartItem.objects.create(
        cart=cart,
        product=product,
        quantity=quantity,
    )


@transaction.atomic
def update_cart_item(
    *,
    cart_item,
    quantity,
):
    """
    Update cart item quantity.
    """
    if not cart_item.is_active:
        raise ValidationError(
            "Cart item not found."
        )
    if cart_item.cart.status is not CartStatus.ACTIVE:
        raise ValidationError(
            "Only active cart items can be updated."
        )
    if quantity < 1:
        raise ValidationError(
            "Quantity must be greater than zero."
        )
    if cart_item.quantity == quantity:
        return cart_item

    cart_item.quantity = quantity

    cart_item.save(
        update_fields=[
            "quantity",
            "updated_at",
        ]
    )

    return cart_item


@transaction.atomic
def remove_cart_item(
    *,
    cart_item,
):
    """
    Soft delete a cart item.
    """

    if cart_item.cart.status != CartStatus.ACTIVE:
        raise ValidationError(
            "Only active cart items can be removed."
        )

    cart_item.soft_delete()

    return cart_item
