# cms_api/tasks.py
from celery import shared_task

from cms_api.services.scheduling import run_scheduled_publishing


@shared_task
def run_scheduled_publishing_task():
    """Periodic task scheduled by Celery Beat (CELERY_BEAT_SCHEDULE)."""
    return run_scheduled_publishing()
