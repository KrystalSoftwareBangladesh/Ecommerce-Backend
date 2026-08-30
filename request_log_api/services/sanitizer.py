# request_log_api/services/sanitizer.py
"""
Centralised sensitive-data sanitization.

Everything a request log persists passes through this module: request and
response payloads, query parameters, multipart form fields, allow-listed
headers, structured error details and tracebacks. No caller anywhere else
in the project has to remember which keys are sensitive, which is the
whole point of putting it here.

Sanitization is recursive and value-preserving in shape: a redacted value
is replaced, never removed, so the structure of the original payload stays
readable.
"""
import json
import re

from request_log_api.constants import (
    MAX_SANITIZE_DEPTH,
    REDACTED_MARKER,
    TRUNCATED_MARKER,
)
from request_log_api.services import config


def is_sensitive_key(key):
    """
    Whether a mapping key names a value that must never be stored.
    """
    if not isinstance(key, str):
        return False

    normalized = key.strip().lower()

    if normalized in config.sensitive_exact_keys():
        return True

    return any(
        fragment in normalized
        for fragment in config.sensitive_key_fragments()
    )


def sanitize(value, depth=0):
    """
    Recursively redact sensitive values in `value`.

    Dictionaries are walked by key, sequences element by element. A
    structure nested deeper than `MAX_SANITIZE_DEPTH` is replaced with a
    marker rather than walked further, so a hostile or cyclic payload
    cannot turn logging into a stack overflow.
    """
    if depth > MAX_SANITIZE_DEPTH:
        return TRUNCATED_MARKER

    if isinstance(value, dict):
        return {
            key: (
                REDACTED_MARKER
                if is_sensitive_key(key)
                else sanitize(item, depth + 1)
            )
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [sanitize(item, depth + 1) for item in value]

    return value


def sanitize_text(text):
    """
    Redact `key=value` and `key: value` pairs naming a sensitive key.

    Used for tracebacks and other free text, where a sensitive value can
    appear inside a rendered frame rather than under a key of its own.
    Free text cannot be parsed reliably, so this is a safety net on top of
    the structured sanitization above, not a replacement for it.
    """
    if not text:
        return ''

    return _SENSITIVE_TEXT_PATTERN.sub(
        lambda match: f'{match.group("key")}{match.group("sep")}'
                      f'{REDACTED_MARKER}',
        text,
    )


def sanitize_traceback(text):
    """
    Sanitize a traceback and cap it at the configured length.
    """
    sanitized = sanitize_text(text)
    limit = config.max_traceback_length()

    if len(sanitized) > limit:
        return f'{sanitized[:limit]}\n{TRUNCATED_MARKER}'

    return sanitized


def sanitize_body(raw, content_type, max_bytes):
    """
    Turn a raw request or response body into something safe to persist.

    Only JSON is decoded and stored structurally. Anything else - HTML,
    binary, an unparseable body - is reported by a marker, because a
    request log is an observability record, not a copy of the traffic.

    Returns `None` when there is no body worth recording.
    """
    if not raw:
        return None

    if len(raw) > max_bytes:
        return {'detail': TRUNCATED_MARKER, 'size_bytes': len(raw)}

    if not _is_json_content_type(content_type):
        return None

    try:
        decoded = json.loads(raw)
    except (ValueError, TypeError):
        return None

    return sanitize(decoded)


def _is_json_content_type(content_type):
    base = (content_type or '').split(';')[0].strip().lower()

    return base.endswith('json')


def _build_sensitive_text_pattern():
    """
    Compile one alternation covering every configured sensitive name.

    Built once at import time from the packaged constants; a deployment
    that overrides the key lists still gets full structural sanitization,
    which is the layer that matters.
    """
    from request_log_api import constants

    names = sorted(
        set(constants.SENSITIVE_EXACT_KEYS)
        | set(constants.SENSITIVE_KEY_FRAGMENTS),
        key=len,
        reverse=True,
    )
    alternation = '|'.join(re.escape(name) for name in names)

    return re.compile(
        r'(?P<key>[\'"]?[\w.-]*(?:' + alternation + r')[\w.-]*[\'"]?)'
        r'(?P<sep>\s*[:=]\s*)'
        # Consume to the end of the value: a header-style value such as
        # "Bearer <jwt>" contains a space, so stopping at whitespace
        # would leave the secret half in place. Commas, closing brackets
        # and newlines still end it, so neighbouring keys survive.
        r'[^\n,;)}\]]+',
        re.IGNORECASE,
    )


_SENSITIVE_TEXT_PATTERN = _build_sensitive_text_pattern()
