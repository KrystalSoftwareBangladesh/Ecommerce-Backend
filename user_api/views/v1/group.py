from rest_framework import viewsets, permissions
from rest_framework.response import Response
from rest_framework import status

from django.contrib.auth.models import Group

from user_api.serializers import GroupSerializer


class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        permissions.IsAdminUser
    ]

    def create(self, request, *args, **kwargs):
        request.data['permission_ids'] = request.data.pop('permissions', [])

        return super().create(request, *args, **kwargs)

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
