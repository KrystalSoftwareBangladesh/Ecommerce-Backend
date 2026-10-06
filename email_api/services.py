# email_api/services.py
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from email.mime.image import MIMEImage

from email_api.constants import EmailStatus
from email_api.models.email_log import EmailLog


class EmailService:

    @staticmethod
    def send(
        *,
        email_type,
        recipient,
        subject,
        template,
        context=None,
        related_user=None,
        metadata=None,
    ):
        context = context or {}

        text_message = render_to_string(
            template,
            context,
        )

        html_template = template.rsplit(".", 1)[0] + ".html"

        html_message = render_to_string(
            html_template,
            context,
        )

        email_log = EmailLog.objects.create(
            email_type=email_type,
            status=EmailStatus.PENDING,
            recipient=recipient,
            sender=settings.DEFAULT_FROM_EMAIL,
            subject=subject,
            provider="smtp",
            related_user=related_user,
            metadata=metadata or {},
        )

        try:
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[recipient],
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
