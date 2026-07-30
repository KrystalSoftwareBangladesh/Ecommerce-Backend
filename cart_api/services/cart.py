# cart_api/services/cart.py
from cart_api.models import Cart


def add_to_cart(*, user, product, quantity):
    cart_item = Cart.objects.filter(
        created_by=user,
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
            ]
        )

        return cart_item

    return Cart.objects.create(
        created_by=user,
        product=product,
        quantity=quantity,
    )


def update_cart_item(*, cart, quantity):
    cart.quantity = quantity
    cart.save(update_fields=["quantity"])

    return cart


def remove_cart_item(*, cart):
    cart.soft_delete()
