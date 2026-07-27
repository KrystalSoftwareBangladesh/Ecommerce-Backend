# wishlist_api/admin.py
from django.contrib import admin

from wishlist_api.models import Wishlist


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "product",
        "created_by",
        "created_at",
        "is_active",
    )
    list_display_links = ['product',]

    list_filter = (
        "is_active",
        "created_at",
    )

    search_fields = (
        "product__name",
        "created_by__username",
        "created_by__email",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
        "deleted_at",
    )

    ordering = ("-created_at",)
