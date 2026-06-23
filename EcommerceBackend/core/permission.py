# EcommerceBackend/core/permission.py
from rest_framework import permissions


class PublicReadPermissionMixin:
    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.AllowAny()]
        return super().get_permissions()
