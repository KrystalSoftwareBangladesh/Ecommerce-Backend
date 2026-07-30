# cart_api/services/cart_item.py
from django.db import transaction
from rest_framework.exceptions import ValidationError

from cart_api.models import Cart, CartItem, CartStatus
from product_api.models import Product


class CartItemService:
    @staticmethod
    def list(cart: Cart):
        CartItemService._ensure_cart_operable(cart)

        return (
            CartItem.objects.filter(
                cart=cart,
                is_active=True,
            )
            .select_related("product")
            .order_by("created_at")
        )

    @staticmethod
    @transaction.atomic
    def add(
        cart: Cart,
        product: Product,
        quantity: int = 1,
    ):
        CartItemService._ensure_cart_operable(cart)

        if quantity < 1:
            raise ValidationError(
                {
                    "quantity": "Quantity must be at least 1."
                }
            )

        cart_item = CartItem.objects.filter(
            cart=cart,
            product=product,
        ).first()

        if cart_item:
            if cart_item.is_active:
                cart_item.quantity += quantity
            else:
                cart_item.is_active = True
                cart_item.deleted_at = None
                cart_item.quantity = quantity

            cart_item.save(
                update_fields=[
                    "quantity",
                    "is_active",
                    "deleted_at",
                    "updated_at",
                ]
            )

            return cart_item

        return CartItem.objects.create(
            cart=cart,
            product=product,
            quantity=quantity,
        )

    @staticmethod
    @transaction.atomic
    def update(
        cart_item: CartItem,
        quantity: int,
    ):
        CartItemService._ensure_cart_operable(
            cart_item.cart
        )

        if quantity < 1:
            raise ValidationError(
                {
                    "quantity": "Quantity must be at least 1."
                }
            )

        cart_item.quantity = quantity

        cart_item.save(
            update_fields=[
                "quantity",
                "updated_at",
            ]
        )

        return cart_item

    @staticmethod
    @transaction.atomic
    def increase_quantity(
        cart_item: CartItem,
        quantity: int = 1,
    ):
        CartItemService._ensure_cart_operable(
            cart_item.cart
        )

        if quantity < 1:
            raise ValidationError(
                {
                    "quantity": "Quantity must be at least 1."
                }
            )

        cart_item.quantity += quantity

        cart_item.save(
            update_fields=[
                "quantity",
                "updated_at",
            ]
        )

        return cart_item

    @staticmethod
    @transaction.atomic
    def decrease_quantity(
        cart_item: CartItem,
        quantity: int = 1,
    ):
        CartItemService._ensure_cart_operable(
            cart_item.cart
        )

        if quantity < 1:
            raise ValidationError(
                {
                    "quantity": "Quantity must be at least 1."
                }
            )

        if cart_item.quantity <= quantity:
            cart_item.soft_delete()
            return None

        cart_item.quantity -= quantity

        cart_item.save(
            update_fields=[
                "quantity",
                "updated_at",
            ]
        )

        return cart_item

    @staticmethod
    @transaction.atomic
    def remove(
        cart_item: CartItem,
    ):
        CartItemService._ensure_cart_operable(
            cart_item.cart
        )

        cart_item.soft_delete()

    @staticmethod
    def _ensure_cart_operable(
        cart: Cart,
    ):
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
