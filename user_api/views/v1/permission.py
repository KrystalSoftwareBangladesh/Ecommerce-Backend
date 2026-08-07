# user_api/views/v1/permission.py
from rest_framework import generics, permissions
from django.contrib.auth.models import Permission

from drf_spectacular.utils import extend_schema

from EcommerceBackend.core.filter import SearchFilter

from user_api.serializers import PermissionSerializer


@extend_schema(tags=["Permissions & Groups"])
class PermissionListView(generics.ListAPIView):
    queryset = Permission.objects.all().order_by('content_type_id', 'id')
    serializer_class = PermissionSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        permissions.IsAdminUser
    ]
    filter_backends = [SearchFilter]
    search_fields = [
        'codename', 'name',
    ]
