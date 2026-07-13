# product_api/admin.py
from django.contrib import admin
from django.db.models import Sum, Value
from django.db.models.functions import Coalesce

from .models import (
    Product, ProductPriceHistory, ProductVariant,
    Brand, ProductImage,
    # InventoryMovement
)
from .services import set_product_image_default


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'get_categories',
                    'current_selling_price', 'is_active']
    list_filter = ['is_active', 'categories']
    search_fields = ['name']

    def get_categories(self, obj):
        return ", ".join(c.name for c in obj.categories.all())

    get_categories.short_description = "Categories"


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


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = [
        'product', 'image', 'display_order', 'is_default', 'is_active']
    list_filter = ['is_active', 'is_default', 'product']
    search_fields = ['product__name', 'alt_text']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
        if obj.is_default:
            set_product_image_default(obj, updated_by=request.user)


# @admin.register(InventoryMovement)
# class InventoryMovementAdmin(admin.ModelAdmin):
#     list_display = ['product_variant', 'quantity',
#                     'movement_type', 'created_at', 'created_by']
#     list_filter = ['movement_type', 'created_at']
#     search_fields = ['product_variant__sku']
#     readonly_fields = ['created_at', 'created_by']
