# cart_api/services/cart.py
from django.conf import settings
from django.db import transaction

from rest_framework.exceptions import ValidationError

from cart_api.models import Cart, CartStatus


def create_cart(
    *,
    user,
    name,
    type,
):
    active_cart_count = Cart.objects.filter(
        created_by=user,
        status=CartStatus.ACTIVE,
        is_active=True,
    ).count()

    max_active_carts = getattr(
        settings,
        "CART_MAX_ACTIVE_CARTS",
        10,
    )

    if active_cart_count >= max_active_carts:
        raise ValidationError(
            {
                "detail": (
                    f"You can have at most "
                    f"{max_active_carts} active carts."
                )
            }
        )

    with transaction.atomic():
        Cart.objects.filter(
            created_by=user,
            is_default=True,
            is_active=True,
        ).update(
            is_default=False,
            updated_by=user,
        )

        return Cart.objects.create(
            name=name,
            type=type,
            status=CartStatus.ACTIVE,
            is_default=True,
            created_by=user,
            updated_by=user,
        )


@transaction.atomic
def update_cart(
    *,
    cart,
    user,
    **validated_data,
):
    if cart.status != CartStatus.ACTIVE:
        raise ValidationError(
            {
                "detail": (
                    "Only active carts can be updated."
                )
            }
        )

    for field, value in validated_data.items():
        setattr(cart, field, value)

    cart.updated_by = user
    cart.save()

    return cart


@transaction.atomic
def set_default_cart(
    *,
    cart,
    user,
):
    if not cart.is_active:
        raise ValidationError(
            {
                "detail": (
                    "Deleted carts cannot be set as default."
                )
            }
        )

    if cart.status != CartStatus.ACTIVE:
        raise ValidationError(
            {
                "detail": (
                    "Only active carts can be set as default."
                )
            }
        )

    Cart.objects.filter(
        created_by=user,
        is_default=True,
        is_active=True,
    ).exclude(
        pk=cart.pk,
    ).update(
        is_default=False,
        updated_by=user,
    )

    cart.is_default = True
    cart.updated_by = user
    cart.save(
        update_fields=[
            "is_default",
            "updated_by",
            "updated_at",
        ]
    )

    return cart


@transaction.atomic
def checkout_cart(
    *,
    cart,
    user,
):
    if cart.status != CartStatus.ACTIVE:
        raise ValidationError(
            {
                "detail": (
                    "Only active carts can be checked out."
                )
            }
        )

    cart.status = CartStatus.CHECKED_OUT
    cart.is_default = False
    cart.updated_by = user
    cart.save(
        update_fields=[
            "status",
            "is_default",
            "updated_by",
            "updated_at",
        ]
    )

    return create_cart(
        user=user,
        name="My Cart",
        type=cart.type,
    )


@transaction.atomic
def abandon_cart(
    *,
    cart,
    user,
):
    if cart.status != CartStatus.ACTIVE:
        raise ValidationError(
            {
                "detail": (
                    "Only active carts can be abandoned."
                )
            }
        )

    cart.status = CartStatus.ABANDONED
    cart.is_default = False
    cart.updated_by = user
    cart.save(
        update_fields=[
            "status",
            "is_default",
            "updated_by",
            "updated_at",
        ]
    )

    return cart


@transaction.atomic
def get_or_create_default_cart(
    *,
    user,
):
    cart = Cart.objects.filter(
        created_by=user,
        status=CartStatus.ACTIVE,
        is_default=True,
        is_active=True,
    ).first()

    if cart:
        return cart

    cart_type = (
        Cart.objects.model.type.field.related_model.objects.filter(
            is_active=True,
        ).first()
    )

    if cart_type is None:
        raise ValidationError(
            {
                "detail": (
                    "No active cart type is available."
                )
            }
        )

    return create_cart(
        user=user,
        name="My Cart",
        type=cart_type,
    )


@transaction.atomic
def delete_cart(
    *,
    cart,
    user,
):
    if not cart.is_active:
        raise ValidationError(
            {
                "detail": "Cart is already deleted."
            }
        )

    was_default = cart.is_default

    cart.updated_by = user
    cart.save(
        update_fields=[
            "updated_by",
            "updated_at",
        ]
    )

    cart.soft_delete()

    if was_default:
        next_cart = Cart.objects.filter(
            created_by=user,
            status=CartStatus.ACTIVE,
            is_active=True,
        ).exclude(
            pk=cart.pk,
        ).first()

        if next_cart:
            set_default_cart(
                cart=next_cart,
                user=user,
            )

    return cart
