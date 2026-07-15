# EcommerceBackend/core/permission.py
from rest_framework import permissions


class PublicReadPermissionMixin:
    public_actions = ["list", "retrieve"]

    def get_permissions(self):
        if self.action in self.public_actions:
            return [permissions.AllowAny()]
        return super().get_permissions()
