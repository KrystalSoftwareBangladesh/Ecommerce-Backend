from django.contrib import admin

from django.contrib.auth.models import Permission
from user_api.models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['id', 'full_name', 'username', 'email', 'is_deleted']
    list_per_page = 10
    list_display_links = ('full_name', 'username', 'email')

    def save_model(self, request, obj, form, change):
        if "password" in form.changed_data:
            obj.set_password(obj.password)

        super().save_model(request, obj, form, change)


class PermissionAdmin(admin.ModelAdmin):
    list_display = ('name', 'codename', 'content_type')
    search_fields = ('name', 'codename')
    list_filter = ('content_type',)

    def get_queryset(self, request):
        """
            Ensure permissions are displayed under the 'Authentication and
            Authorization' section.
        """
        queryset = super().get_queryset(request)
        queryset.model._meta.app_label = 'auth'
        return queryset

    def has_add_permission(self, request):
        """Disable the Add button."""
        return False

    def has_change_permission(self, request, obj=None):
        """Disable editing existing records."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Disable the delete button."""
        return False


admin.site.register(Permission, PermissionAdmin)
