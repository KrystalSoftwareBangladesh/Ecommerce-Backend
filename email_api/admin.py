# email_api/admin.py
from django.contrib import admin

from email_api.models import EmailLog, EmailVerification


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "email_type",
        "recipient",
        "subject",
        "status",
        "provider",
        "sent_at",
        "created_at",
    )
    list_filter = (
        "email_type",
        "status",
        "provider",
        "created_at",
    )
    search_fields = (
        "recipient",
        "subject",
        "provider_message_id",
        "idempotency_key",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "sent_at",
        "provider_message_id",
    )
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_per_page = 50


@admin.register(EmailVerification)
class EmailVerificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "token_hash",
        "expires_at",
        "verified_at",
        "created_at",
    )
    list_filter = (
        "verified_at",
        "expires_at",
        "created_at",
    )
    search_fields = (
        "user__email",
        "user__username",
        "token_hash",
    )
    readonly_fields = (
        "user",
        "token_hash",
        "expires_at",
        "verified_at",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_per_page = 50
