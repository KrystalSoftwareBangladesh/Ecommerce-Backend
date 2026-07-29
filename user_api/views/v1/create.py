from rest_framework import generics, permissions

from drf_spectacular.utils import extend_schema

from user_api.models import User

from user_api.serializers import UserProfileSerializer


@extend_schema(tags=["Users"])
class CreateUserView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserProfileSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        permissions.IsAdminUser
    ]
