# email_api/services/__init__.py
from .email import EmailDeliveryError, EmailService
from .email_verification import EmailVerificationService
from .order_notification import (
    create_order_notification_recipient,
    delete_order_notification_recipient,
    describe_staff_actor,
    queue_order_notifications,
    schedule_order_notifications,
    update_order_notification_recipient,
)


__all__ = [
    "EmailDeliveryError",
    "EmailService",
    "EmailVerificationService",
    "create_order_notification_recipient",
    "delete_order_notification_recipient",
    "describe_staff_actor",
    "queue_order_notifications",
    "schedule_order_notifications",
    "update_order_notification_recipient",
]
