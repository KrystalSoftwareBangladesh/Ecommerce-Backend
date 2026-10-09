# email_api/serializers/__init__.py
from .email_verification import (
    EmailVerificationConfirmResponseSerializer,
    EmailVerificationConfirmSerializer,
)


__all__ = [
    'EmailVerificationConfirmResponseSerializer',
    'EmailVerificationConfirmSerializer',
]
