# email_api/services.py
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from email.mime.image import MIMEImage

from email_api.constants import (
    EMAIL_TEMPLATE_REGISTRY,
    EmailStatus,
)
from email_api.models.email_log import EmailLog


class EmailService:

    @staticmethod
    def create_log(
        *,
        email_type,
        recipient,
        related_user=None,
        metadata=None,
    ):
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
            )

            email.attach_alternative(
                html_message,
                "text/html",
            )

            logo_path = (
                Path(__file__).resolve().parent
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

            email_log.status = EmailStatus.SENT
            email_log.sent_at = timezone.now()

            email_log.save(
                update_fields=[
                    "status",
                    "sent_at",
                    "updated_at",
                ],
            )

            return email_log

        except Exception as exc:
            email_log.status = EmailStatus.FAILED
            email_log.error_message = str(exc)

            email_log.save(
                update_fields=[
                    "status",
                    "error_message",
                    "updated_at",
                ],
            )

            raise
