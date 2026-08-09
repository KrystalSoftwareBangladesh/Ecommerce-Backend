# user_api/views/v1/permission.py
from rest_framework.filters import SearchFilter
from rest_framework import generics

from django.db.models import Q

from drf_spectacular.utils import extend_schema

from django.contrib.auth.models import Permission

from user_api.serializers import PermissionSerializer


@extend_schema(tags=["Permissions & Groups"])
class PermissionListView(generics.ListAPIView):
    serializer_class = PermissionSerializer
    filter_backends = [SearchFilter]
    search_fields = [
        'codename', 'name',
    ]

    def get_queryset(self):
        user = self.request.user

        user_permissions = user.get_all_permissions()

        if not user_permissions:
            return Permission.objects.none()

        permission_filter = Q()

        for permission in user_permissions:
            app_label, codename = permission.split(".", 1)

            permission_filter |= Q(
                content_type__app_label=app_label,
                codename=codename,
            )

        return (
            Permission.objects
            .filter(permission_filter)
            .select_related("content_type")
            .order_by("content_type_id", "id")
        )
