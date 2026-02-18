# purchase_api/admin.py
from django.contrib import admin
from .models import Purchase, PurchaseItem


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ['id', 'supplier', 'purchase_date',
                    'invoice_number', 'status', 'total_amount', 'is_active']
    list_filter = ['status', 'purchase_date', 'is_active']
    search_fields = ['invoice_number', 'supplier__name']
    readonly_fields = ['created_at', 'updated_at',
                       'created_by', 'updated_by', 'is_active']


@admin.register(PurchaseItem)
class PurchaseItemAdmin(admin.ModelAdmin):
    list_display = ['purchase', 'product_variant',
                    'quantity', 'unit_cost', 'line_total']
    list_filter = ['purchase__status']
    search_fields = ['product_variant__sku']
    readonly_fields = ['line_total']
