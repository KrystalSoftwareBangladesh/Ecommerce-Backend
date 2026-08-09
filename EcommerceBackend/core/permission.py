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

    GET/HEAD/OPTIONS  -> view
    POST              -> add
    PUT/PATCH         -> change
    DELETE            -> delete
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
