# cart_api/services/cart.py
from django.conf import settings
from django.db import transaction
from rest_framework.exceptions import ValidationError

from cart_api.models import Cart, CartStatus, CartType


class CartService:
    @staticmethod
    def list(user):
        return Cart.objects.filter(
            created_by=user,
            is_active=True,
        ).select_related("type")

    @staticmethod
    def get(cart_id: int, user):
        return Cart.objects.get(
            id=cart_id,
            created_by=user,
            is_active=True,
        )

    @staticmethod
    def get_default(user):
        return (
            Cart.objects.filter(
                created_by=user,
                is_active=True,
                status=CartStatus.ACTIVE,
                is_default=True,
            )
            .select_related("type")
            .first()
        )

    @staticmethod
    @transaction.atomic
    def get_or_create_default(user):
        cart = CartService.get_default(user)

        if cart:
            return cart

        cart_type = CartType.objects.filter(
            is_active=True,
        ).order_by("id").first()

        if not cart_type:
            raise ValidationError(
                {
                    "detail": "No active cart type found."
                }
            )

        return CartService.create(
            user=user,
            validated_data={
                "name": cart_type.name,
                "type": cart_type,
            },
        )

    @staticmethod
    @transaction.atomic
    def create(user, validated_data: dict):
        active_cart_count = Cart.objects.filter(
            created_by=user,
            is_active=True,
            status=CartStatus.ACTIVE,
        ).count()

        if active_cart_count >= settings.CART_MAX_ACTIVE_CARTS:
            raise ValidationError(
                {
                    "detail": (
                        f"You can have maximum "
                        f"{settings.CART_MAX_ACTIVE_CARTS} active carts."
                    )
                }
            )

        Cart.objects.filter(
            created_by=user,
            is_active=True,
            status=CartStatus.ACTIVE,
            is_default=True,
        ).update(
            is_default=False,
        )

        cart = Cart.objects.create(
            created_by=user,
            updated_by=user,
            name=validated_data["name"],
            type=validated_data["type"],
            status=CartStatus.ACTIVE,
            is_default=True,
        )

        return cart

    @staticmethod
    @transaction.atomic
    def update(cart: Cart, validated_data: dict):
        CartService._ensure_operable(cart)

        if "name" in validated_data:
            cart.name = validated_data["name"]

        if "type" in validated_data:
            cart.type = validated_data["type"]

        if validated_data.get("is_default", False):
            CartService._set_default(cart)

        cart.save()

        return cart

    @staticmethod
    @transaction.atomic
    def checkout(cart: Cart):
        CartService._ensure_operable(cart)

        if not cart.items.filter(is_active=True).exists():
            raise ValidationError(
                {
                    "detail": "Cannot checkout an empty cart."
                }
            )

        cart.status = CartStatus.CHECKED_OUT
        cart.is_default = False
        cart.save(
            update_fields=[
                "status",
                "is_default",
                "updated_at",
            ]
        )

        CartService.get_or_create_default(
            cart.created_by,
        )

        return cart

    @staticmethod
    @transaction.atomic
    def abandon(cart: Cart):
        CartService._ensure_operable(cart)

        cart.status = CartStatus.ABANDONED
        cart.is_default = False

        cart.save(
            update_fields=[
                "status",
                "is_default",
                "updated_at",
            ]
        )

        CartService.get_or_create_default(
            cart.created_by,
        )

        return cart

    @staticmethod
    @transaction.atomic
    def delete(cart: Cart):
        was_default = cart.is_default

        cart.soft_delete()

        if was_default:
            next_cart = (
                Cart.objects.filter(
                    created_by=cart.created_by,
                    is_active=True,
                    status=CartStatus.ACTIVE,
                )
                .exclude(id=cart.id)
                .order_by("-updated_at")
                .first()
            )

            if next_cart:
                next_cart.is_default = True
                next_cart.save(
                    update_fields=[
                        "is_default",
                        "updated_at",
                    ]
                )

    @staticmethod
    @transaction.atomic
    def set_default(cart: Cart):
        CartService._ensure_operable(cart)
        CartService._set_default(cart)

        return cart

    @staticmethod
    def _ensure_operable(cart: Cart):
        if cart.status == CartStatus.CHECKED_OUT:
            raise ValidationError(
                {
                    "detail": (
                        "Checked out cart cannot be modified."
                    )
                }
            )

        if cart.status == CartStatus.ABANDONED:
            raise ValidationError(
                {
                    "detail": (
                        "Abandoned cart cannot be modified."
                    )
                }
            )

    @staticmethod
    def _set_default(cart: Cart):
        Cart.objects.filter(
            created_by=cart.created_by,
            is_active=True,
            status=CartStatus.ACTIVE,
            is_default=True,
        ).exclude(
            id=cart.id,
        ).update(
            is_default=False,
        )

        cart.is_default = True

        cart.save(
            update_fields=[
                "is_default",
                "updated_at",
            ]
        )
