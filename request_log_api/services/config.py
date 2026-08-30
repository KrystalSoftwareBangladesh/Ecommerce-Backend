# request_log_api/services/config.py
"""
Deployment-time configuration for request logging.

Every value defaults to the constant of the same name in
`request_log_api.constants` and can be overridden with a `REQUEST_LOG_`
prefixed setting, so the trusted proxy depth, the size limits and the
sensitive key list are all configuration rather than code.
"""
from django.conf import settings

from request_log_api import constants


def get_setting(name, default):
    """
    Read `REQUEST_LOG_<name>`, falling back to the packaged default.
    """
    return getattr(settings, f'REQUEST_LOG_{name}', default)


def is_enabled():
    return bool(get_setting('ENABLED', True))


def excluded_path_prefixes():
    return tuple(
        get_setting(
            'EXCLUDED_PATH_PREFIXES',
            constants.EXCLUDED_PATH_PREFIXES,
        )
    )


def trusted_proxy_count():
    return int(
        get_setting('TRUSTED_PROXY_COUNT', constants.TRUSTED_PROXY_COUNT)
    )


def max_request_body_bytes():
    return int(
        get_setting(
            'MAX_REQUEST_BODY_BYTES',
            constants.MAX_REQUEST_BODY_BYTES,
        )
    )


def max_response_body_bytes():
    return int(
        get_setting(
            'MAX_RESPONSE_BODY_BYTES',
            constants.MAX_RESPONSE_BODY_BYTES,
        )
    )


def max_traceback_length():
    return int(
        get_setting(
            'MAX_TRACEBACK_LENGTH',
            constants.MAX_TRACEBACK_LENGTH,
        )
    )


def sensitive_exact_keys():
    return frozenset(
        key.lower()
        for key in get_setting(
            'SENSITIVE_EXACT_KEYS',
            constants.SENSITIVE_EXACT_KEYS,
        )
    )


def sensitive_key_fragments():
    return tuple(
        fragment.lower()
        for fragment in get_setting(
            'SENSITIVE_KEY_FRAGMENTS',
            constants.SENSITIVE_KEY_FRAGMENTS,
        )
    )


def storage_path():
    return get_setting(
        'STORAGE',
        'request_log_api.services.storage.DatabaseRequestLogStorage',
    )
