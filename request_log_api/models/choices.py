# request_log_api/models/choices.py
from django.db import models


class RequestOutcome(models.TextChoices):
    """
    Derived classification of how a request ended.

    The HTTP status code stays the source of truth; this exists so
    filtering and aggregation do not have to reason about ranges.

    `EXCEPTION` is narrower than `SERVER_ERROR`: it means the view raised
    something no handler caught, so an exception type and a traceback were
    recorded alongside the 500.
    """
    SUCCESS = 'SUCCESS', 'Success'
    CLIENT_ERROR = 'CLIENT_ERROR', 'Client Error'
    SERVER_ERROR = 'SERVER_ERROR', 'Server Error'
    EXCEPTION = 'EXCEPTION', 'Exception'


class ClientType(models.TextChoices):
    """
    Which client application made the request.

    Taken from an explicit `X-Client-Type` header rather than inferred, so
    an unset value stays honestly `UNKNOWN` instead of being guessed from
    a User-Agent.
    """
    WEB = 'WEB', 'Web'
    MOBILE = 'MOBILE', 'Mobile'
    ADMIN = 'ADMIN', 'Admin'
    EXTERNAL = 'EXTERNAL', 'External'
    UNKNOWN = 'UNKNOWN', 'Unknown'


class DeviceType(models.TextChoices):
    DESKTOP = 'DESKTOP', 'Desktop'
    MOBILE = 'MOBILE', 'Mobile'
    TABLET = 'TABLET', 'Tablet'
    BOT = 'BOT', 'Bot'
    UNKNOWN = 'UNKNOWN', 'Unknown'
