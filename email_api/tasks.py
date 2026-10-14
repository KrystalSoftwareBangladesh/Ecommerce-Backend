# email_api/tasks.py
from celery import shared_task
from django.utils import timezone

from email_api.constants import EmailStatus
from email_api.models.email_log import EmailLog
from email_api.services.email import (
    EmailDeliveryError,
    EmailService,
    recover_stale_email_logs,
)


@shared_task(
    bind=True,
    max_retries=3,
)
def send_email_task(self, email_log_id, context=None):
    # Claim the log atomically. A duplicate or re-dispatched task
    # for a log that is already being sent, sent or failed does
    # nothing, so an email is never sent twice by this task.
    claimed = EmailLog.objects.filter(
        id=email_log_id,
        status=EmailStatus.PENDING,
    ).update(
        status=EmailStatus.PROCESSING,
        updated_at=timezone.now(),
    )
    if not claimed:
        return

    email_log = EmailLog.objects.get(
        id=email_log_id,
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

    except Exception as exc:
        # Not a delivery failure (e.g. a template that does not
        # render): retrying cannot help, so fail the log instead of
        # leaving it PROCESSING.
        email_log.status = EmailStatus.FAILED
        email_log.error_message = f"{type(exc).__name__}: {exc}"
        email_log.save(
            update_fields=[
                "status",
                "error_message",
                "updated_at",
            ],
        )
        raise


@shared_task
def recover_stale_email_logs_task():
    """Periodic task scheduled by Celery Beat (CELERY_BEAT_SCHEDULE)."""
    return recover_stale_email_logs()
