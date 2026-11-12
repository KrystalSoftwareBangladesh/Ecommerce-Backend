# cms_api/admin.py
from django.contrib import admin

from cms_api.models import (
    CmsMediaConfig,
    CmsNavigationItem,
    CmsNavigationMenu,
)


@admin.register(CmsMediaConfig)
class CmsMediaConfigAdmin(admin.ModelAdmin):
    list_display = (
        "max_image_upload_size",
        "max_document_upload_size",
        "updated_at",
    )

    def has_add_permission(self, request):
        # Singleton: never offer "Add" once the one row exists.
        return not CmsMediaConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


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
