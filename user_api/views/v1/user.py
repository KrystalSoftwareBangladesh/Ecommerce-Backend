# user_api/views/v1/user.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from rest_framework.decorators import action
from rest_framework import generics, permissions
from rest_framework import status
from rest_framework import viewsets

from drf_spectacular.utils import extend_schema, OpenApiResponse

from EcommerceBackend.core.permission import ModelPermissionAccess

from user_api.models import User
from user_api.serializers import (
    UserProfileSerializer, AssignGroupSerializer, RemoveGroupSerializer,
    UserExistenceCheckSerializer, UserListSerializer, UserDetailSerializer,
    UserCreateSerializer, UserUpdateSerializer,
)


@extend_schema(tags=["Users"])
class UserProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        """
            Return the authenticated user with groups
            and permissions prefetched.
        """
        return User.objects.filter(
            pk=self.request.user.pk
        ).prefetch_related(
            'groups',
            'user_permissions',
            'groups__permissions',
        ).first()

    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)


@extend_schema(tags=["Users"])
class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserProfileSerializer
    permission_classes = [
        ModelPermissionAccess,
    ]

    def get_queryset(self):
        queryset = (
            User.objects
            .filter(is_deleted=False)
            .order_by("-added_at", "-id")
        )

        if self.action == "list":
            queryset = queryset.prefetch_related("groups")

        return queryset

    def get_serializer_class(self):
        if self.action == "list":
            return UserListSerializer

        if self.action == "retrieve":
            return UserDetailSerializer

        if self.action == "create":
            return UserCreateSerializer

        if self.action in ["update", "partial_update"]:
            return UserUpdateSerializer

        if self.action == "assign_role":
            return AssignGroupSerializer

        if self.action == "remove_role":
            return RemoveGroupSerializer

        return UserDetailSerializer

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        if user.pk == request.user.pk:
            raise PermissionDenied(
                "You cannot delete your own user account."
            )

        user.delete()

        return Response(
            {
                "success": True,
                "message": "User deleted successfully.",
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        request=AssignGroupSerializer,
        responses={
            200: OpenApiResponse(
                description="Role assigned successfully."
            ),
        },
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="assign-role",
    )
    def assign_role(self, request, *args, **kwargs):
        user = self.get_object()

        serializer = AssignGroupSerializer(
            instance=user,
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {
                "success": True,
                "message": "Role assigned successfully.",
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        request=RemoveGroupSerializer,
        responses={
            200: OpenApiResponse(
                description="Role removed successfully."
            ),
        },
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="remove-role",
    )
    def remove_role(self, request, *args, **kwargs):
        user = self.get_object()

        serializer = RemoveGroupSerializer(
            instance=user,
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {
                "success": True,
                "message": "Role removed successfully.",
            },
            status=status.HTTP_200_OK,
        )


@extend_schema(tags=["Users"])
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
