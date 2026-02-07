# supplier_api/admin.py
from django.contrib import admin
from .models import Supplier


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'contact_person',
        'phone',
        'email',
        'payment_type',
        'credit_days',
        'display_categories',  # renamed for clarity
        'is_active',
        'created_at',
    ]
    list_filter = ['payment_type', 'is_active', 'categories']
    search_fields = ['name', 'phone', 'email']
    filter_horizontal = ['categories']
    readonly_fields = [
        'created_at',
        'updated_at',
        'created_by',
        'updated_by',
        'is_active',
        'deleted_at',
    ]

    def display_categories(self, obj):
        return ", ".join([str(category) for category in obj.categories.all()]) if obj.categories.exists() else "-"  # noqa

    display_categories.short_description = 'Categories'
    # allows sorting by category name if needed
    display_categories.admin_order_field = 'categories'
