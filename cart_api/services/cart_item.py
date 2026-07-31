# cart_api/services/cart_item.py
from django.db import transaction

from rest_framework.exceptions import ValidationError

from cart_api.models import CartItem, CartStatus
from cart_api.services.cart import get_or_create_default_cart


@transaction.atomic
def add_cart_item(
    *,
    user,
    product,
    quantity,
):
    cart = get_or_create_default_cart(user=user)

    if cart.status != CartStatus.ACTIVE:
        raise ValidationError(
            {
                "detail": (
                    "Items can only be added to an active cart."
                )
            }
        )

    cart_item = CartItem.objects.filter(
        cart=cart,
        product=product,
        is_active=True,
    ).first()

    if cart_item:
        cart_item.quantity += quantity
        cart_item.updated_by = user
        cart_item.save(
            update_fields=[
                "quantity",
                "updated_by",
                "updated_at",
            ]
        )
        return cart_item

    return CartItem.objects.create(
        cart=cart,
        product=product,
        quantity=quantity,
        created_by=user,
        updated_by=user,
    )


@transaction.atomic
def update_cart_item(
    *,
    cart_item,
    user,
    quantity,
):
    if cart_item.cart.status != CartStatus.ACTIVE:
        raise ValidationError(
            {
                "detail": (
                    "Only items in an active cart can be updated."
                )
            }
        )

    if quantity < 1:
        raise ValidationError(
            {
                "quantity": (
                    "Quantity must be greater than zero."
                )
            }
        )

    cart_item.quantity = quantity
    cart_item.updated_by = user
    cart_item.save(
        update_fields=[
            "quantity",
            "updated_by",
            "updated_at",
        ]
    )

    return cart_item


@transaction.atomic
def remove_cart_item(
    *,
    cart_item,
    user,
):
    if cart_item.cart.status != CartStatus.ACTIVE:
        raise ValidationError(
            {
                "detail": (
                    "Only items in an active cart can be removed."
                )
            }
        )

    cart_item.updated_by = user
    cart_item.save(
        update_fields=[
            "updated_by",
            "updated_at",
        ]
    )

    cart_item.soft_delete()

    return cart_item
