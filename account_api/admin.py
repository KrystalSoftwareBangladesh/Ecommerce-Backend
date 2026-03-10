from django.contrib import admin

from account_api.models import ChartOfAccount


@admin.register(ChartOfAccount)
class ChartOfAccountAdmin(admin.ModelAdmin):
    list_display = (
        'code',
        'name',
        'account_type',
        'parent',
        'is_active',
    )
    search_fields = ('code', 'name')
    list_filter = ('account_type', 'is_active')
