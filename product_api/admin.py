# product_api/admin.py
from django.contrib import admin
from django.db.models import Sum, Value
from django.db.models.functions import Coalesce

from .models import (
    Product, ProductPriceHistory, ProductVariant,
    # InventoryMovement
)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'current_selling_price', 'is_active']
    list_filter = ['is_active', 'category']
    search_fields = ['name']


@admin.register(ProductPriceHistory)
class ProductPriceHistoryAdmin(admin.ModelAdmin):
    list_display = ['product', 'price', 'changed_at', 'changed_by']
    list_filter = ['changed_at']
    search_fields = ['product__name']


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ['sku', 'product', 'color',
                    'size', 'current_stock', 'is_active']
    list_filter = ['is_active', 'product']
    search_fields = ['sku', 'product__name']

    def current_stock(self, obj):
        return obj.movements.aggregate(
            stock=Coalesce(Sum('quantity'), Value(0))
        )['stock']

    current_stock.short_description = 'Current Stock'


# @admin.register(InventoryMovement)
# class InventoryMovementAdmin(admin.ModelAdmin):
#     list_display = ['product_variant', 'quantity',
#                     'movement_type', 'created_at', 'created_by']
#     list_filter = ['movement_type', 'created_at']
#     search_fields = ['product_variant__sku']
#     readonly_fields = ['created_at', 'created_by']
