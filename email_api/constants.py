# email_api/constants.py
from django.db import models


class EmailStatus(models.IntegerChoices):
    PENDING = 1, 'Pending'
    PROCESSING = 2, "Processing"
    SENT = 3, 'Sent'
    FAILED = 4, 'Failed'


class EmailType(models.TextChoices):
    WELCOME = 'WELCOME', 'Welcome'
    EMAIL_VERIFICATION = 'EMAIL_VERIFICATION', 'Email Verification'
    PASSWORD_RESET = 'PASSWORD_RESET', 'Password Reset'
    PASSWORD_CHANGED = 'PASSWORD_CHANGED', 'Password Changed'
    ORDER_CONFIRMATION = 'ORDER_CONFIRMATION', 'Order Confirmation'
    ORDER_CANCELLED = 'ORDER_CANCELLED', 'Order Cancelled'
    ORDER_SHIPPED = 'ORDER_SHIPPED', 'Order Shipped'
    CAMPAIGN = 'CAMPAIGN', 'Campaign'


EMAIL_TEMPLATE_REGISTRY = {
    EmailType.WELCOME: {
        "subject": "Welcome to Best Computer Hub",
        "text": "emails/welcome.txt",
        "html": "emails/welcome.html",
    },
    EmailType.EMAIL_VERIFICATION: {
        "subject": "Verify your email address",
        "text": "emails/email_verification.txt",
        "html": "emails/email_verification.html",
    },
    EmailType.PASSWORD_CHANGED: {
        "subject": "Your password has been changed",
        "text": "emails/password_changed.txt",
        "html": "emails/password_changed.html",
    },
    EmailType.PASSWORD_RESET: {
        "subject": "Reset your Best Computer Hub password",
        "text": "emails/password_reset.txt",
        "html": "emails/password_reset.html",
    },
}
