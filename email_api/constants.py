# email_api/constants.py
from django.db import models


class EmailStatus(models.IntegerChoices):
    PENDING = 1, 'Pending'
    SENT = 2, 'Sent'
    FAILED = 3, 'Failed'


class EmailType(models.TextChoices):
    WELCOME = 'WELCOME', 'Welcome'
    EMAIL_VERIFICATION = 'EMAIL_VERIFICATION', 'Email Verification'
    PASSWORD_RESET = 'PASSWORD_RESET', 'Password Reset'
    PASSWORD_CHANGED = 'PASSWORD_CHANGED', 'Password Changed'
    ORDER_CONFIRMATION = 'ORDER_CONFIRMATION', 'Order Confirmation'
    ORDER_CANCELLED = 'ORDER_CANCELLED', 'Order Cancelled'
    ORDER_SHIPPED = 'ORDER_SHIPPED', 'Order Shipped'
    CAMPAIGN = 'CAMPAIGN', 'Campaign'
