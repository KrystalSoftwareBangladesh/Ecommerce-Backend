# cart_api/services/cart_type.py
from django.db import transaction
from django.utils.text import slugify

from rest_framework.exceptions import ValidationError

from cart_api.models import CartType


def create_cart_type(
    *,
    user,
    name: str,
    description: str = "",
    is_active: bool = True,
):
    slug = slugify(name)

    if CartType.objects.filter(slug=slug).exists():
        raise ValidationError(
            {"name": "A cart type with this name already exists."}
        )

    return CartType.objects.create(
        name=name,
        slug=slug,
        description=description,
        is_active=is_active,
        created_by=user,
        updated_by=user,
    )


@transaction.atomic
def update_cart_type(
    *,
    cart_type: CartType,
    user,
    **validated_data,
):
    if "name" in validated_data:
        slug = slugify(validated_data["name"])

        if (
            CartType.objects.exclude(pk=cart_type.pk)
            .filter(slug=slug)
            .exists()
        ):
            raise ValidationError(
                {"name": "A cart type with this name already exists."}
            )

        cart_type.slug = slug

    for field, value in validated_data.items():
        setattr(cart_type, field, value)

    cart_type.updated_by = user
    cart_type.save()

    return cart_type


@transaction.atomic
def deactivate_cart_type(
    *,
    cart_type: CartType,
    user,
):
    if cart_type.carts.filter(is_active=True).exists():
        raise ValidationError(
            {
                "detail": (
                    "Cannot deactivate a cart type that is "
                    "used by active carts."
                )
            }
        )

    cart_type.is_active = False
    cart_type.updated_by = user
    cart_type.save(
        update_fields=[
            "is_active",
            "updated_by",
            "updated_at",
        ]
    )

    return cart_type
