# cart_api/admin.py
from django.contrib import admin

from cart_api.models import (
    Cart,
    CartItem,
)


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    autocomplete_fields = [
        "product",
    ]
    readonly_fields = [
        "created_at",
        "updated_at",
    ]


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "created_by",
        "status",
        "created_at",
        "updated_at",
        "is_active",
    ]

    list_filter = [
        "status",
        "is_active",
        "created_at",
    ]

    search_fields = [
        "id",
        "created_by__username",
        "created_by__email",
        "created_by__first_name",
        "created_by__last_name",
    ]

    readonly_fields = [
        "created_at",
        "updated_at",
        "deleted_at",
    ]

    autocomplete_fields = [
        "created_by",
        "updated_by",
    ]

    ordering = [
        "-created_at",
    ]

    inlines = [
        CartItemInline,
    ]


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "cart",
        "product",
        "quantity",
        "created_at",
        "is_active",
    ]

    list_filter = [
        "is_active",
        "created_at",
    ]

    search_fields = [
        "id",
        "product__name",
        "cart__created_by__username",
        "cart__created_by__email",
        "cart__created_by__first_name",
        "cart__created_by__last_name",
    ]

    autocomplete_fields = [
        "cart",
        "product",
    ]

    readonly_fields = [
        "created_at",
        "updated_at",
        "deleted_at",
    ]

    ordering = [
        "-created_at",
    ]
