# banner_api/admin.py
from django.contrib import admin

from banner_api.models import Banner, BannerPlacement


@admin.register(BannerPlacement)
class BannerPlacementAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "code",
        "is_active",
        "created_at",
        "updated_at",
    ]
    list_filter = [
        "is_active",
    ]
    search_fields = [
        "name",
        "code",
    ]
    readonly_fields = [
        "created_at",
        "updated_at",
        "deleted_at",
    ]


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "placement",
        "display_order",
        "is_active",
        "start_at",
        "end_at",
        "created_at",
    ]
    list_filter = [
        "placement",
        "is_active",
        "start_at",
        "end_at",
    ]
    search_fields = [
        "title",
        "subtitle",
    ]
    ordering = [
        "placement",
        "display_order",
        "-created_at",
    ]
    readonly_fields = [
        "created_at",
        "updated_at",
        "deleted_at",
        "created_by",
        "updated_by",
    ]
