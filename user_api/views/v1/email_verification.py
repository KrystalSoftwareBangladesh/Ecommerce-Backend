# user_api/views/v1/email_verification.py
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import UserRateThrottle

from datetime import timedelta
from django.utils import timezone
from drf_spectacular.utils import extend_schema

from email_api.models import EmailVerification
from email_api.constants import EmailType
from email_api.services.email import EmailService
from email_api.services.email_verification import (
    EmailVerificationService,
)


class EmailVerificationRequestThrottle(UserRateThrottle):
    scope = "email_verification_request"
    rate = "1/5minutes"


@extend_schema(tags=["Authentication"])
class EmailVerificationRequestView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [EmailVerificationRequestThrottle]

    def post(self, request):
        user = request.user

        if not user.email:
            return Response(
                {"message": "Your account has no email address."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # if user.email_verified if hasattr(user, "email_verified") else False:
        #     return Response(
        #         {"message": "Your email is already verified."},
        #         status=status.HTTP_400_BAD_REQUEST,
        #     )
        if EmailVerification.objects.filter(
            user=user,
            verified_at__isnull=False,
        ).exists():
            return Response(
                {"message": "Your email is already verified."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        recent_verification = EmailVerification.objects.filter(
            user=user,
            created_at__gte=timezone.now() - timedelta(minutes=5),
        ).exists()

        if recent_verification:
            return Response(
                {
                    "message": (
                        "A verification request was made recently. "
                        "Please wait 5 minutes before trying again."
                    )
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        verification, raw_token = EmailVerificationService.create(
            user=user,
        )

        from django.conf import settings

        verification_url = (
            f"{settings.FRONTEND_BASE_URL.rstrip('/')}"
            f"/verify-email?token={raw_token}"
        )

        EmailService.queue(
            email_type=EmailType.EMAIL_VERIFICATION,
            recipient=user.email,
            context={
                "user_name": user.full_name or user.email,
                "verification_url": verification_url,
            },
            related_user=user,
            metadata={
                "verification_id": verification.id,
            },
            idempotency_key=(
                f"EMAIL_VERIFICATION:{verification.id}"
            ),
        )

        return Response(
            {"message": "Verification email sent."},
            status=status.HTTP_200_OK,
        )
