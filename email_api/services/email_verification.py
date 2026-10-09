# email_api/services/email_verification.py
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.utils import timezone

import hashlib
import secrets

from email_api.models.email_verification import EmailVerification


class EmailVerificationService:

    TOKEN_EXPIRY_HOURS = 24
    TOKEN_LENGTH = 32

    @staticmethod
    def _hash_token(token):
        return hashlib.sha256(
            token.encode("utf-8")
        ).hexdigest()

    @classmethod
    def create(cls, user):
        if not user.email:
            raise ValidationError(
                "User does not have an email address."
            )

        raw_token = secrets.token_urlsafe(
            cls.TOKEN_LENGTH
        )

        token_hash = cls._hash_token(raw_token)

        expires_at = timezone.now() + timedelta(
            hours=cls.TOKEN_EXPIRY_HOURS
        )

        verification = EmailVerification.objects.create(
            user=user,
            token_hash=token_hash,
            expires_at=expires_at,
        )

        return verification, raw_token

    @classmethod
    def verify(cls, raw_token):
        token_hash = cls._hash_token(raw_token)

        verification = (
            EmailVerification.objects
            .select_related("user")
            .filter(
                token_hash=token_hash,
                verified_at__isnull=True,
            )
            .first()
        )

        if not verification:
            raise ValidationError(
                "Invalid verification token."
            )

        if verification.is_expired:
            raise ValidationError(
                "Verification token has expired."
            )

        verification.verified_at = timezone.now()
        verification.save(
            update_fields=[
                "verified_at",
                "updated_at",
            ],
        )

        return verification.user
