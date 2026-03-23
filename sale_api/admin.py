# sale_api/admin.py
from django.contrib import admin
from .models import PaymentMethod, Sale, SaleItem


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = [
        'code',
        'name',
        'default_account',
        'allow_account_override',
        'is_active',
        'sort_order',
    ]
    list_filter = ['is_active', 'allow_account_override']
    search_fields = ['code', 'name']


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'customer',
        'payment_method',
        'account',
        'sale_date',
        'invoice_number',
        'channel',
        'status',
        'total_amount',
    ]
    list_filter = ['channel', 'status', 'sale_date']
    search_fields = ['invoice_number']


@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    list_display = ['sale', 'product_variant',
                    'quantity', 'unit_price', 'line_total']
