# sale_api/admin.py
from django.contrib import admin
from .models import Sale, SaleItem


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer', 'sale_date',
                    'invoice_number', 'channel', 'status', 'total_amount',]
    list_filter = ['channel', 'status', 'sale_date']
    search_fields = ['invoice_number']


@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    list_display = ['sale', 'product_variant',
                    'quantity', 'unit_price', 'line_total']
