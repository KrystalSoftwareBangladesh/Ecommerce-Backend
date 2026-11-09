# cms_api/admin.py
from django.contrib import admin

from cms_api.models import CmsNavigationItem, CmsNavigationMenu


@admin.register(CmsNavigationMenu)
class CmsNavigationMenuAdmin(admin.ModelAdmin):
    list_display = ("name", "key", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "key")
    ordering = ("name",)


@admin.register(CmsNavigationItem)
class CmsNavigationItemAdmin(admin.ModelAdmin):
    list_display = (
        "label",
        "menu",
        "parent",
        "link_type",
        "is_visible",
        "sort_order",
    )
    list_filter = ("menu", "link_type", "is_visible")
    search_fields = ("label", "external_url")
    ordering = ("menu", "parent", "sort_order")
