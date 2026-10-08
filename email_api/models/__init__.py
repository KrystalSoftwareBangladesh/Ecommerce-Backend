# email_api/models/__init__.py
from .email_log import EmailLog
from .email_verification import EmailVerification

__all__ = [
    "EmailLog",
    "EmailVerification",
]
