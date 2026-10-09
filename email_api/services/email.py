# email_api/services/email.py
from pathlib import Path

from django.db import IntegrityError, transaction
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.utils import timezone
from email.mime.image import MIMEImage

from email_api.constants import (
    EMAIL_TEMPLATE_REGISTRY,
    EmailStatus,
)
from email_api.models.email_log import EmailLog


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
    ):
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

        from email_api.tasks import send_email_task

        transaction.on_commit(
            lambda: send_email_task.delay(
                email_log.id,
                context or {},
            )
        )

        return email_log
