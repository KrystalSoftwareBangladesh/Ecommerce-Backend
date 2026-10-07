# email_api/tasks.py
from celery import shared_task
from email_api.services import EmailService
from email_api.models.email_log import EmailLog


@shared_task
def send_email_task(email_log_id, context=None):
    email_log = EmailLog.objects.get(
        id=email_log_id,
    )

    EmailService.send(
        email_log,
        context=context,
    )
