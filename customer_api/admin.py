from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import CustomerProfile


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = [
        "full_name_link",
        "email",
        "phone",
        "customer_type",
        "is_active",
        "created_at",
    ]
    list_filter = ["customer_type", "is_active", "created_at"]
    search_fields = [
        "user__first_name",
        "user__middle_name",
        "user__last_name",
        "user__email",
        "phone",
        "facebook_profile_url",
    ]
    readonly_fields = ["created_at", "updated_at"]
    fields = [
        "user",
        "phone",
        "facebook_profile_url",
        "customer_type",
        "notes",
        "is_active",
        "created_at",
        "updated_at",
    ]

    def full_name_link(self, obj):
        if not obj.user:
            return "-"
        url = reverse("admin:user_api_user_change", args=[obj.user.id])
        return format_html(
            '<a href="{}">{}</a>', url, obj.user.full_name or "No name" # noqa
        )
    full_name_link.short_description = "Full Name"

    def email(self, obj):
        return obj.user.email or "-"
    email.short_description = "Email"
