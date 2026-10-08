# email_api/tasks.py
from celery import shared_task

from email_api.constants import EmailStatus
from email_api.models.email_log import EmailLog
from email_api.services.email import EmailDeliveryError, EmailService


@shared_task(
    bind=True,
    max_retries=3,
)
def send_email_task(self, email_log_id, context=None):
    try:
        email_log = EmailLog.objects.get(
            id=email_log_id,
        )
    except EmailLog.DoesNotExist:
        return

    email_log.status = EmailStatus.PROCESSING
    email_log.save(
        update_fields=[
            "status",
            "updated_at",
        ],
    )

    try:
        EmailService.send(
            email_log,
            context=context,
        )

    except EmailDeliveryError as exc:
        if self.request.retries >= self.max_retries:
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

        email_log.status = EmailStatus.PENDING
        email_log.error_message = str(exc)

        email_log.save(
            update_fields=[
                "status",
                "error_message",
                "updated_at",
            ],
        )

        raise self.retry(
            exc=exc,
            countdown=60,
        )
