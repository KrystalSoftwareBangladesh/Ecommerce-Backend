# EcommerceBackend/core/permission.py
from rest_framework import permissions


class PublicReadPermissionMixin:
    public_actions = ["list", "retrieve"]

    def get_permissions(self):
        if self.action in self.public_actions:
            return [permissions.AllowAny()]
        return super().get_permissions()


class ModelPermissionAccess(permissions.DjangoModelPermissions):
    """
    Enforces Django model permissions for authenticated API requests.

    Standard actions:
        GET/HEAD/OPTIONS  -> view
        POST              -> add
        PUT/PATCH         -> change
        DELETE            -> delete

    Custom actions can be declared on a ViewSet using
    the `custom_permissions` mapping.
    """

    perms_map = {
        "GET": ["%(app_label)s.view_%(model_name)s"],
        "HEAD": ["%(app_label)s.view_%(model_name)s"],
        "OPTIONS": ["%(app_label)s.view_%(model_name)s"],
        "POST": ["%(app_label)s.add_%(model_name)s"],
        "PUT": ["%(app_label)s.change_%(model_name)s"],
        "PATCH": ["%(app_label)s.change_%(model_name)s"],
        "DELETE": ["%(app_label)s.delete_%(model_name)s"],
    }

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        custom_permissions = getattr(
            view,
            "custom_permissions",
            {},
        )

        action = getattr(view, "action", None)

        if action in custom_permissions:
            permission = custom_permissions[action]

            app_label = view.get_queryset().model._meta.app_label

            return request.user.has_perm(
                f"{app_label}.{permission}"
            )

        return super().has_permission(request, view)


class CustomPermissionAccessMixin:
    """
    Applies `ModelPermissionAccess` only to the actions declared in the
    ViewSet `custom_permissions` mapping.

    Every other action keeps the permission classes already configured
    on the ViewSet, so adding a custom permission to a single action
    never changes how the remaining endpoints are protected.

    Example:

        custom_permissions = {
            "mark_as_menu": "mark_category_as_menu",
        }
    """

    custom_permissions = {}

    def get_permissions(self):
        if self.action in self.custom_permissions:
            return [ModelPermissionAccess()]

        return super().get_permissions()
