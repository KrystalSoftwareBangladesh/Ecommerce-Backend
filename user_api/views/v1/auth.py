# user_api/views/v1/auth.py
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from rest_framework.throttling import AnonRateThrottle
from rest_framework import permissions
from rest_framework import status
from rest_framework import generics
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import (
    urlsafe_base64_decode,
    urlsafe_base64_encode,
)
from django.conf import settings

from drf_spectacular.utils import extend_schema

import logging
import uuid

from user_api.models import User
from user_api.serializers import (
    TokenSerializer, ChangePasswordSerializer, CustomerSignupSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
)
from email_api.constants import EmailType
from email_api.services import EmailService


logger = logging.getLogger(__name__)


@extend_schema(tags=["Authentication"])
class LoginView(TokenObtainPairView):
    serializer_class = TokenSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


@extend_schema(tags=["Authentication"])
class TokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            response.data["message"] = "Access token refreshed successfully"

        return response


@extend_schema(
    tags=["Authentication"],
    request=None,
    responses={200: None},
)
class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if not refresh_token:
                return Response({
                    "error": "Refresh token is required"
                }, status=status.HTTP_400_BAD_REQUEST)

            token = RefreshToken(refresh_token)
            token.blacklist()

            return Response({
                "message": "Successfully logged out"
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(e)
            return Response({
                "error": "Invalid token or token already used"
            }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["Authentication"])
class ChangePasswordView(generics.UpdateAPIView):
    queryset = User.objects.filter(is_deleted=False)
    serializer_class = ChangePasswordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        """
            Ensure user can only change their own password.
        """
        return self.request.user

    def patch(self, request, *args, **kwargs):
        """
            Handle partial updates for password change.
        """
        serializer = self.get_serializer(data=request.data, context={'request': request})   # noqa
        serializer.is_valid(raise_exception=True)
        user = self.get_object()
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])

        if user.email:
            EmailService.queue(
                email_type=EmailType.PASSWORD_CHANGED,
                recipient=user.email,
                context={
                    "user_name": user.full_name or user.email,
                },
                related_user=user,
                idempotency_key=f"PASSWORD_CHANGED:{user.id}:{uuid.uuid4()}",    # noqa
            )

        return Response({
            "message": "Password changed successfully!"
        }, status=status.HTTP_200_OK)


@extend_schema(tags=["Authentication"])
class RegisterView(generics.CreateAPIView):
    """
    Public customer registration endpoint.
    Creates User + CustomerProfile atomically.
    Returns customer data with JWT tokens.
    """
    serializer_class = CustomerSignupSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        """Handle customer registration."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer_data = serializer.save()

        return Response(
            {
                'message': 'Customer registered successfully',
                'data': customer_data,
            },
            status=status.HTTP_201_CREATED
        )


class PasswordResetRequestThrottle(AnonRateThrottle):
    scope = "password_reset_request"
    rate = "5/hour"


@extend_schema(
    tags=["Authentication"],
    request=PasswordResetRequestSerializer,
    responses={200: None},
)
class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [PasswordResetRequestThrottle]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].strip()

        user = User.objects.filter(
            email__iexact=email,
            is_active=True,
            is_deleted=False,
        ).first()

        if user and user.email:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = PasswordResetTokenGenerator().make_token(user)

            reset_url = (
                f"{settings.FRONTEND_BASE_URL.rstrip('/')}"
                f"/reset-password?uid={uid}&token={token}"
            )

            EmailService.queue(
                email_type=EmailType.PASSWORD_RESET,
                recipient=user.email,
                context={
                    "user_name": user.full_name or user.email,
                    "reset_url": reset_url,
                },
                related_user=user,
                idempotency_key=(
                    f"PASSWORD_RESET:{user.id}:{uuid.uuid4()}"
                ),
            )

        return Response(
            {
                "message": (
                    "If an account exists with that email address, "
                    "a password reset link will be sent."
                )
            },
            status=status.HTTP_200_OK,
        )


@extend_schema(
    tags=["Authentication"],
    request=PasswordResetConfirmSerializer,
    responses={200: None},
)
class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = []

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)

        uid = serializer.validated_data["uid"]
        token = serializer.validated_data["token"]

        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(
                pk=user_id,
                is_active=True,
                is_deleted=False,
            )
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response(
                {"message": "Invalid or expired reset link."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        token_generator = PasswordResetTokenGenerator()

        if not token_generator.check_token(user, token):
            return Response(
                {"message": "Invalid or expired reset link."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])

        if user.email:
            EmailService.queue(
                email_type=EmailType.PASSWORD_CHANGED,
                recipient=user.email,
                context={
                    "user_name": user.full_name or user.email,
                },
                related_user=user,
                idempotency_key=(
                    f"PASSWORD_RESET_CONFIRMED:{user.id}:{uuid.uuid4()}"
                ),
            )

        return Response(
            {"message": "Password reset successfully."},
            status=status.HTTP_200_OK,
        )
