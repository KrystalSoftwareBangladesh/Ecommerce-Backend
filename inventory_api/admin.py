from django.contrib import admin
from .models import InventoryMovement, InventoryReservation

# Register your models here.


@admin.register(InventoryMovement)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'product_variant', 'quantity',
        'movement_type', 'reference_type',
    ]
    list_filter = ['movement_type', 'reference_type', 'is_active']
    search_fields = [
        'product_variant__sku', 'product_variant__product__name',
        'movement_type'
    ]
    readonly_fields = [
        'created_at', 'updated_at', 'created_by', 'updated_by', 'is_active'
    ]


@admin.register(InventoryReservation)
class InventoryReservationAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'product_variant',
        'sale',
        'quantity',
        'status',
        'expires_at',
        'created_at',
    ]
    list_filter = ['status', 'created_at']
    search_fields = [
        'product_variant__sku',
        'product_variant__product__name',
        'sale__invoice_number',
    ]
    readonly_fields = [
        'created_at', 'updated_at',
        'created_by', 'updated_by',
    ]
