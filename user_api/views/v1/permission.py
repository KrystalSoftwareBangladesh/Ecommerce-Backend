from rest_framework import generics, permissions

from ZayrahLifeBackend.core.filter import SearchFilter

from django.contrib.auth.models import Permission

from user_api.serializers import PermissionSerializer


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
