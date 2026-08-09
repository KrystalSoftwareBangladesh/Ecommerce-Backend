# user_api/views/v1/group.py
from rest_framework.response import Response
from rest_framework.filters import SearchFilter
from rest_framework import viewsets
from rest_framework import status

from drf_spectacular.utils import extend_schema

from EcommerceBackend.core.permission import ModelPermissionAccess

from django.contrib.auth.models import Group

from user_api.serializers import GroupSerializer


@extend_schema(tags=["Permissions & Groups"])
class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.all().order_by('name', 'id')
    serializer_class = GroupSerializer
    permission_classes = [
        ModelPermissionAccess,
    ]
    filter_backends = [SearchFilter]
    search_fields = ['name',]

    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    def perform_destroy(self, instance):
        instance.delete()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)

        return Response({
            "message": "Role has been successfully deleted."
        }, status=status.HTTP_200_OK)
