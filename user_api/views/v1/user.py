from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import generics, permissions
from rest_framework import status

from drf_spectacular.utils import extend_schema

from user_api.models import User

from user_api.serializers import UserProfileSerializer
from user_api.serializers import AssignGroupSerializer
from user_api.serializers import UserExistenceCheckSerializer


class UserProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        """
            Return the authenticated user.
        """
        return self.request.user

    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)


class UserListView(generics.ListAPIView):
    queryset = User.objects.filter(is_deleted=False)
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]


class AssignGroupView(generics.UpdateAPIView):
    queryset = User.objects.filter(is_deleted=False)
    serializer_class = AssignGroupSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        permissions.IsAdminUser,
    ]


class UserExistenceCheckView(APIView):
    """
    POST /user/v1/verify/
    Check if a user exists by email or username.
    """
    serializer_class = UserExistenceCheckSerializer

    @extend_schema(
        request=UserExistenceCheckSerializer,
        responses={200: None},
        summary="Verify if a user exists by email or username",
        description="Accepts either an email or username and returns whether the user exists.", # noqa
    )
    def post(self, request):
        serializer = UserExistenceCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = None
        if data.get("email"):
            user = User.objects.filter(email=data["email"]).first()
            field = "email"
            value = data["email"]
        elif data.get("username"):
            user = User.objects.filter(username=data["username"]).first()
            field = "username"
            value = data["username"]

        if user:
            return Response(
                {"exists": True, "field": field, "value": value},
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"exists": False},
                status=status.HTTP_200_OK,
            )
