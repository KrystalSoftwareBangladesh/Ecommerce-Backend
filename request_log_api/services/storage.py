# request_log_api/services/storage.py
"""
Where a built request log event is persisted.

The middleware and the builder know nothing about the database. They
produce a plain dict and hand it to `persist_request_log`, which resolves
the configured storage backend and writes it.

That indirection is the only thing standing between today's PostgreSQL
table and a different logging backend later: a future backend is a new
`RequestLogStorage` subclass plus a `REQUEST_LOG_STORAGE` setting, with no
change to the middleware, the builder or the sanitizer.
"""
import logging

from django.utils.module_loading import import_string

from request_log_api.services import config


logger = logging.getLogger(__name__)


class RequestLogStorage:
    """
    Interface every request log backend implements.
    """

    def save(self, event):
        raise NotImplementedError


class DatabaseRequestLogStorage(RequestLogStorage):
    """
    Writes one row to the main database.
    """

    def save(self, event):
        from request_log_api.models import RequestLog

        return RequestLog.objects.create(**event)


def get_storage():
    """
    Instantiate the configured storage backend.
    """
    return import_string(config.storage_path())()


def persist_request_log(event):
    """
    Best-effort write. Never raises.

    Request logging is an observability layer, not a dependency of the
    application: a failure here is recorded against this module's logger
    and swallowed, so the API response the caller already received is
    never affected.
    """
    try:
        get_storage().save(event)
    except Exception:                                       # noqa: BLE001
        logger.exception('Failed to persist API request log')
