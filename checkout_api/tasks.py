# checkout_api/tasks.py
from celery import shared_task

from checkout_api.services import expire_pending_orders


@shared_task
def expire_pending_orders_task():
    """Periodic task scheduled by Celery Beat (CELERY_BEAT_SCHEDULE)."""
    cancelled, released = expire_pending_orders()
    return {
        "cancelled_orders": cancelled,
        "released_reservations": released,
    }
