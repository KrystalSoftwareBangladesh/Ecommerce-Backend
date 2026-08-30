# request_log_api/admin.py
from django.contrib import admin

from request_log_api.models import RequestLog


@admin.register(RequestLog)
class RequestLogAdmin(admin.ModelAdmin):
    """
    Read-only view of the request log.

    Records are written by the middleware and are immutable: adding,
    changing and deleting are all disabled here, matching the API, so the
    log cannot be edited through any normal path. Retention and cleanup
    are a controlled operational process, not an admin action.
    """
    list_display = (
        "created_at",
        "request_method",
        "request_path",
        "status_code",
        "outcome",
        "duration_ms",
        "user",
        "ip_address",
    )
    list_filter = (
        "outcome",
        "request_method",
        "is_authenticated",
        "is_success",
        "is_bot",
        "client_type",
        "device_type",
    )
    search_fields = (
        "request_id",
        "request_path",
        "route_pattern",
        "anonymous_id",
        "exception_type",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at", "-id")

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
