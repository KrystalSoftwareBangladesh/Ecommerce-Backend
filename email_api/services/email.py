# email_api/services/email.py
import json
import logging
from datetime import timedelta
from pathlib import Path

from django.db import IntegrityError, transaction
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.template.loader import render_to_string
from django.utils import timezone
from email.mime.image import MIMEImage

from email_api.constants import (
    EMAIL_TEMPLATE_REGISTRY,
    EmailStatus,
)
from email_api.models.email_log import EmailLog


logger = logging.getLogger(__name__)

# A log untouched for this long is no longer being worked on: the
# Celery retry countdown is 60 seconds and there are 3 retries.
STALE_EMAIL_AFTER = timedelta(minutes=15)
MAX_RECOVERY_ATTEMPTS = 3


class EmailDeliveryError(Exception):
    """Raised when email delivery fails temporarily."""


class EmailService:

    @staticmethod
    def create_log(
        *,
        email_type,
        recipient,
        related_user=None,
        metadata=None,
        idempotency_key=None,
    ):
        if not recipient:
            raise ValidationError("Email recipient is required.")

        if not email_type:
            raise ValidationError("Email type is required.")

        template_config = EMAIL_TEMPLATE_REGISTRY.get(email_type)

        if not template_config:
            raise ValueError(
                f"No email template configured for: {email_type}"
            )

        return EmailLog.objects.create(
            email_type=email_type,
            status=EmailStatus.PENDING,
            recipient=recipient,
            sender=settings.DEFAULT_FROM_EMAIL,
            subject=template_config["subject"],
            provider="smtp",
            related_user=related_user,
            metadata=metadata or {},
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def send(email_log, context=None):
        context = context or {}

        template_config = EMAIL_TEMPLATE_REGISTRY.get(
            email_log.email_type
        )

        if not template_config:
            raise ValueError(
                f"No email template configured for: "
                f"{email_log.email_type}"
            )

        text_message = render_to_string(
            template_config["text"],
            context,
        )

        html_message = render_to_string(
            template_config["html"],
            context,
        )

        try:
            email = EmailMultiAlternatives(
                subject=email_log.subject,
                body=text_message,
                from_email=email_log.sender,
                to=[email_log.recipient],
                connection=None,
                headers=None,
            )

            email.attach_alternative(
                html_message,
                "text/html",
            )

            logo_path = (
                Path(__file__).resolve().parent.parent
                / "static"
                / "email"
                / "round_logo_best_computer_hub.png"
            )

            with open(logo_path, "rb") as logo_file:
                logo = MIMEImage(
                    logo_file.read(),
                    _subtype="png",
                )

            logo.add_header(
                "Content-ID",
                "<bchl-logo>",
            )

            logo.add_header(
                "Content-Disposition",
                "inline",
                filename="round_logo_best_computer_hub.png",
            )

            email.attach(logo)

            email.send(
                fail_silently=False,
            )

            message_id = email.message().get("Message-ID")

            email_log.status = EmailStatus.SENT
            email_log.sent_at = timezone.now()
            email_log.provider_message_id = message_id or ""

            email_log.save(
                update_fields=[
                    "status",
                    "sent_at",
                    "provider_message_id",
                    "updated_at",
                ],
            )

            return email_log

        except Exception as exc:
            raise EmailDeliveryError(str(exc)) from exc

    @staticmethod
    def queue(
        *,
        email_type,
        recipient,
        context=None,
        related_user=None,
        metadata=None,
        idempotency_key=None,
        persist_context=False,
    ):
        """
        Create an EmailLog and send it through Celery after commit.

        ``persist_context`` stores the template context on the log
        so the email can be resent if dispatch is lost. Leave it
        off for emails whose context holds secrets (tokens, links).
        """
        if persist_context:
            context = json.loads(
                json.dumps(context or {}, cls=DjangoJSONEncoder)
            )
            metadata = {**(metadata or {}), "context": context}

        if idempotency_key:
            existing_log = EmailLog.objects.filter(
                idempotency_key=idempotency_key,
            ).first()

            if existing_log:
                return existing_log

        try:
            with transaction.atomic():
                email_log = EmailService.create_log(
                    email_type=email_type,
                    recipient=recipient,
                    related_user=related_user,
                    metadata=metadata,
                    idempotency_key=idempotency_key,
                )
        except IntegrityError:
            if not idempotency_key:
                raise

            email_log = EmailLog.objects.get(
                idempotency_key=idempotency_key,
            )

        transaction.on_commit(
            lambda: dispatch_send_task(
                email_log.id,
                context or {},
            )
        )

        return email_log


def dispatch_send_task(email_log_id, context, raise_errors=True):
    """
    Hand an email to Celery.

    If the broker is unreachable the log stays PENDING with the
    reason recorded, so ``recover_stale_email_logs`` can retry it.
    """
    from email_api.tasks import send_email_task

    try:
        send_email_task.delay(email_log_id, context)
    except Exception as exc:
        logger.exception(
            "Could not dispatch email log %s.", email_log_id
        )
        EmailLog.objects.filter(
            pk=email_log_id,
            status=EmailStatus.PENDING,
        ).update(
            error_message=f"Dispatch failed: {exc}",
            updated_at=timezone.now(),
        )
        if raise_errors:
            raise


def _recover_pending_log(log_id, cutoff, max_attempts):
    """
    Re-dispatch one stale PENDING log, or fail it if it cannot be
    resent. Returns "redispatched", "failed" or None (skipped).
    """
    with transaction.atomic():
        email_log = (
            EmailLog.objects.select_for_update(skip_locked=True)
            .filter(
                pk=log_id,
                status=EmailStatus.PENDING,
                updated_at__lte=cutoff,
            )
            .first()
        )
        if email_log is None:
            return None

        context = email_log.metadata.get("context")
        attempts = email_log.metadata.get("recovery_attempts", 0)
        if context is None or attempts >= max_attempts:
            email_log.status = EmailStatus.FAILED
            email_log.error_message = (
                "Never sent and no stored context to resend it."
                if context is None
                else f"Not sent after {attempts} recovery attempts."
            )
            email_log.save(
                update_fields=["status", "error_message", "updated_at"]
            )
            return "failed"

        email_log.metadata = {
            **email_log.metadata,
            "recovery_attempts": attempts + 1,
        }
        email_log.save(update_fields=["metadata", "updated_at"])

    dispatch_send_task(log_id, context, raise_errors=False)
    return "redispatched"


def recover_stale_email_logs(
    stale_after=STALE_EMAIL_AFTER,
    batch_size=100,
    max_attempts=MAX_RECOVERY_ATTEMPTS,
):
    """
    Stop email logs from staying PENDING or PROCESSING forever.

    - PROCESSING for longer than ``stale_after``: the worker died
      or hung mid-send. The email may already have been delivered,
      so it is marked FAILED, never resent automatically.
    - PENDING for longer than ``stale_after``: it was never picked
      up (broker down, task lost). It is re-dispatched with its
      stored context, at most ``max_attempts`` times; without a
      stored context it is marked FAILED.

    The send task claims a log with a PENDING -> PROCESSING update,
    so a re-dispatched log is sent at most once.
    """
    now = timezone.now()
    cutoff = now - stale_after

    stuck_ids = list(
        EmailLog.objects.filter(
            status=EmailStatus.PROCESSING,
            updated_at__lte=cutoff,
        )
        .order_by("id")
        .values_list("id", flat=True)[:batch_size]
    )
    failed = EmailLog.objects.filter(
        id__in=stuck_ids,
        status=EmailStatus.PROCESSING,
    ).update(
        status=EmailStatus.FAILED,
        error_message=(
            "Stopped while processing; it may already have been "
            "sent, so it was not resent."
        ),
        updated_at=now,
    )

    redispatched = 0
    pending_ids = list(
        EmailLog.objects.filter(
            status=EmailStatus.PENDING,
            updated_at__lte=cutoff,
        )
        .order_by("id")
        .values_list("id", flat=True)[:batch_size]
    )
    for log_id in pending_ids:
        outcome = _recover_pending_log(log_id, cutoff, max_attempts)
        if outcome == "redispatched":
            redispatched += 1
        elif outcome == "failed":
            failed += 1

    return {"redispatched": redispatched, "failed": failed}
