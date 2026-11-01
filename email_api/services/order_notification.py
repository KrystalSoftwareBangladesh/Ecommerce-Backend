# email_api/services/order_notification.py
import logging

from django.conf import settings
from django.db import transaction
from django.db.models import Sum

from email_api.constants import EmailType
from email_api.models import OrderNotificationRecipient
from email_api.services.email import EmailService


logger = logging.getLogger(__name__)

ORDER_NOTIFICATION_SUBJECTS = {
    EmailType.ORDER_PLACED_NOTIFICATION: "New order {invoice} to process",
    EmailType.ORDER_CANCELLED_NOTIFICATION: "Order {invoice} was cancelled",
}


def normalize_recipient_email(email):
    return (email or "").strip().lower()


def create_order_notification_recipient(*, validated_data, user):
    validated_data["email"] = normalize_recipient_email(
        validated_data.get("email")
    )
    return OrderNotificationRecipient.objects.create(
        **validated_data,
        created_by=user,
        updated_by=user,
    )


@transaction.atomic
def update_order_notification_recipient(*, recipient, validated_data, user):
    if "email" in validated_data:
        validated_data["email"] = normalize_recipient_email(
            validated_data["email"]
        )

    for field, value in validated_data.items():
        setattr(recipient, field, value)

    recipient.updated_by = user
    recipient.save()
    return recipient


def delete_order_notification_recipient(*, recipient, user):
    """Soft delete a recipient so it stops receiving notifications."""
    recipient.updated_by = user
    recipient.save(update_fields=["updated_by", "updated_at"])
    recipient.soft_delete()
    return recipient


def get_active_order_notification_emails():
    return list(
        OrderNotificationRecipient.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
        )
        .order_by("id")
        .values_list("id", "email")
    )


def _order_admin_url(sale_id):
    base_url = (getattr(settings, "FRONTEND_BASE_URL", "") or "").rstrip("/")
    if not base_url:
        return ""
    return f"{base_url}/admin/orders/{sale_id}/"


def _display_name(user):
    if user is None:
        return ""
    return (
        getattr(user, "full_name", "")
        or getattr(user, "username", "")
        or getattr(user, "email", "")
    )


def queue_order_notifications(sale_id, email_type, cancelled_by=None):
    """
    Queue one notification per active recipient for an order event.

    Runs after the order transaction commits. It never raises: a
    notification problem must not affect the order itself.
    """
    from sale_api.models import Sale

    try:
        recipients = get_active_order_notification_emails()
        if not recipients:
            return

        sale = (
            Sale.objects.select_related("customer__user")
            .get(pk=sale_id)
        )
        invoice_number = sale.invoice_number or f"#{sale.id}"
        item_count = (
            sale.items.aggregate(total=Sum("quantity"))["total"] or 0
        )
        context = {
            "invoice_number": invoice_number,
            "channel": sale.channel,
            "customer_name": (
                _display_name(sale.customer.user) or "Unknown customer"
            ),
            "item_count": item_count,
            "total_amount": sale.total_amount,
            "currency": "BDT",
            "order_admin_url": _order_admin_url(sale.id),
            "cancelled_by": cancelled_by or "",
        }
        subject = ORDER_NOTIFICATION_SUBJECTS[email_type].format(
            invoice=invoice_number,
        )
    except Exception:
        logger.exception(
            "Could not prepare %s notifications for sale %s.",
            email_type,
            sale_id,
        )
        return

    for recipient_id, email in recipients:
        try:
            EmailService.queue(
                email_type=email_type,
                recipient=email,
                subject=subject,
                metadata={
                    "sale_id": sale_id,
                    "order_notification_recipient_id": recipient_id,
                },
                idempotency_key=(
                    f"sale-{sale_id}-{email_type.lower()}-{recipient_id}"
                ),
                context=context,
                # The alert carries no secrets, so the context can be
                # stored and the email resent if dispatch is lost.
                persist_context=True,
            )
        except Exception:
            logger.exception(
                "Could not queue %s notification for sale %s to "
                "recipient %s.",
                email_type,
                sale_id,
                recipient_id,
            )


def schedule_order_notifications(sale_id, email_type, cancelled_by=None):
    """Queue order notifications once the current transaction commits."""
    transaction.on_commit(
        lambda: queue_order_notifications(
            sale_id,
            email_type,
            cancelled_by=cancelled_by,
        )
    )


def describe_staff_actor(user):
    name = _display_name(user)
    return f"staff ({name})" if name else "staff"
