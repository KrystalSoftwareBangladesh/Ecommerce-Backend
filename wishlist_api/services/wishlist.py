# wishlist_api/services/wishlist.py
from wishlist_api.models import Wishlist


def create_wishlist(*, user, product):
    wishlist_item = Wishlist.objects.filter(
        created_by=user,
        product=product,
    ).first()

    if wishlist_item:
        if wishlist_item.is_active:
            return wishlist_item

        wishlist_item.restore()
        return wishlist_item

    return Wishlist.objects.create(
        product=product,
        created_by=user,
    )


def remove_wishlist(*, wishlist):
    wishlist.soft_delete()
