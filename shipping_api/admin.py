# shipping_api/admin.py
from django.contrib import admin

from .models import (
    ShippingZone,
    ShippingZoneRule,
    ShippingMethod,
    ShippingRate,
)


class ShippingZoneRuleInline(admin.TabularInline):
    model = ShippingZoneRule
    extra = 1
    fields = [
        "match_type",
        "match_value",
    ]


@admin.register(ShippingZone)
class ShippingZoneAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "code",
        "is_default",
        "is_active",
        "display_order",
        "created_at",
    ]
    list_filter = [
        "is_default",
        "is_active",
    ]
    search_fields = ["name", "code"]
    readonly_fields = [
        "created_at",
        "updated_at",
    ]
    fields = [
        "name",
        "code",
        "description",
        "is_default",
        "is_active",
        "display_order",
        "created_at",
        "updated_at",
    ]
    inlines = [ShippingZoneRuleInline]
    list_per_page = 15


@admin.register(ShippingZoneRule)
class ShippingZoneRuleAdmin(admin.ModelAdmin):
    list_display = [
        "zone",
        "match_type",
        "match_value",
    ]
    list_filter = ["match_type"]
    search_fields = [
        "zone__name",
        "match_value",
    ]


@admin.register(ShippingMethod)
class ShippingMethodAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "code",
        "is_active",
        "display_order",
        "created_at",
    ]
    list_filter = ["is_active"]
    search_fields = ["name", "code"]
    readonly_fields = [
        "created_at",
        "updated_at",
    ]
    fields = [
        "name",
        "code",
        "description",
        "is_active",
        "display_order",
        "created_at",
        "updated_at",
    ]
    list_per_page = 15


@admin.register(ShippingRate)
class ShippingRateAdmin(admin.ModelAdmin):
    list_display = [
        "zone",
        "method",
        "base_charge",
        "free_shipping_threshold",
        "is_active",
        "created_at",
    ]
    list_filter = [
        "zone",
        "method",
        "is_active",
    ]
    search_fields = [
        "zone__name",
        "method__name",
    ]
    readonly_fields = [
        "created_at",
        "updated_at",
    ]
    fields = [
        "zone",
        "method",
        "base_charge",
        "free_shipping_threshold",
        "is_active",
        "created_at",
        "updated_at",
    ]
    list_per_page = 15
