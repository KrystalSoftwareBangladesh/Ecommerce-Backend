# request_log_api/services/builder.py
"""
Turns a request/response pair into a request log event.

The builder owns every decision about *what* is recorded; the middleware
owns *when*. The result is a plain dict of `RequestLog` field values -
already sanitized - which the storage layer persists. Nothing here imports
a model, so the same event can be handed to a different backend later.
"""
import re
import time
import traceback as traceback_module
import uuid

from django.utils import timezone

from request_log_api.constants import (
    CAPTURED_HEADERS,
    MULTIPART_CONTENT_TYPE,
    REQUEST_ID_HEADER,
    TRUNCATED_MARKER,
)
from request_log_api.models.choices import RequestOutcome
from request_log_api.services import client, config
from request_log_api.services.sanitizer import (
    sanitize,
    sanitize_body,
    sanitize_traceback,
)


def should_log(request):
    """
    Whether this request produces a log record at all.
    """
    if not config.is_enabled():
        return False

    path = request.path or ''

    return not path.startswith(tuple(config.excluded_path_prefixes()))


def resolve_request_id(request):
    """
    Reuse the client's `X-Request-ID` when it is a valid UUID.

    Anything else - absent, malformed, or an attempt to inject arbitrary
    text into the log - is replaced by a freshly generated identifier.
    """
    supplied = client.header_value(request, REQUEST_ID_HEADER).strip()

    if supplied:
        try:
            return str(uuid.UUID(supplied))
        except (ValueError, AttributeError, TypeError):
            pass

    return str(uuid.uuid4())


def collect_request_context(request):
    """
    Capture everything known before the application runs.

    Called from the middleware's request phase, so the body is still
    unread and the multipart stream is still intact.
    """
    user_agent = client.header_value(request, 'User-Agent')

    context = {
        'request_id': resolve_request_id(request),
        'anonymous_id': client.resolve_anonymous_id(request),
        'ip_address': client.resolve_ip_address(request),
        'forwarded_for': client.forwarded_for(request)[:255],
        'user_agent': user_agent,
        'client_type': client.resolve_client_type(request),
        'origin': client.header_value(request, 'Origin')[:255],
        'referer': client.header_value(request, 'Referer')[:500],
        'frontend_route': client.resolve_frontend_route(request),
        'request_method': (request.method or '')[:10],
        'request_path': (request.path or '')[:500],
        'query_parameters': sanitize(
            {key: request.GET.get(key) for key in request.GET}
        ),
        'query_string': request.META.get('QUERY_STRING', '') or '',
        'headers': _collect_headers(request),
        'request_size_bytes': _content_length(request),
        'started_at': timezone.now(),
    }
    context.update(client.parse_user_agent(user_agent))
    context.update(_collect_payload(request))

    return context


def build_event(request, context, response=None, exception_info=None,
                monotonic_start=None):
    """
    Complete a started context with the outcome of the request.

    `exception_info` is the `(type, value, traceback)` triple stashed by
    the middleware's `process_exception` hook, or `None` when the request
    ended with a response.
    """
    event = dict(context)

    status_code = _resolve_status_code(response)

    event['user'] = _resolve_user(request)
    event['is_authenticated'] = event['user'] is not None
    event['route_pattern'] = _resolve_route_pattern(request)
    event['status_code'] = status_code
    event['response_size_bytes'] = _response_size(response)
    event['response_body'] = _collect_response_body(response)
    event['completed_at'] = timezone.now()
    event['duration_ms'] = _duration_ms(monotonic_start)
    event['is_success'] = status_code < 400
    event['outcome'] = _resolve_outcome(status_code, exception_info)
    event.update(
        _collect_error(status_code, event['response_body'], exception_info)
    )

    return event


def _resolve_user(request):
    """
    The authenticated user, or None.

    DRF writes the authenticated user back onto the underlying Django
    request, so by the response phase this reflects JWT authentication as
    well as session authentication. A failed or absent authentication
    leaves an `AnonymousUser`, and a deleted user leaves nothing - neither
    may raise.
    """
    user = getattr(request, 'user', None)

    if user is None or not getattr(user, 'is_authenticated', False):
        return None

    return user if getattr(user, 'pk', None) else None


def _collect_headers(request):
    """
    Read only the allow-listed headers.

    Authorization, Cookie and any API key header are absent from the list,
    so they are never read into memory as part of a log record.
    """
    headers = {}

    for name in CAPTURED_HEADERS:
        value = client.header_value(request, name)

        if value:
            headers[name] = value[:500]

    return sanitize(headers)


def _content_length(request):
    try:
        return max(int(request.META.get('CONTENT_LENGTH') or 0), 0)
    except (TypeError, ValueError):
        return 0


def _collect_payload(request):
    """
    Capture the request payload without ever storing file contents.

    A multipart request is read through Django's own form parsing, which
    DRF then reuses, so the files are described by their metadata and the
    binary content is dropped.
    """
    payload = {
        'request_body': None,
        'is_multipart': False,
        'form_fields': {},
        'files': [],
        'file_count': 0,
        'total_file_size_bytes': 0,
    }

    content_type = (request.content_type or '').lower()

    if not content_type or request.method in ('GET', 'HEAD', 'OPTIONS'):
        return payload

    if content_type.startswith(MULTIPART_CONTENT_TYPE):
        payload['is_multipart'] = True
        payload.update(_collect_multipart(request))

        return payload

    limit = config.max_request_body_bytes()

    if _content_length(request) > limit:
        payload['request_body'] = {
            'detail': TRUNCATED_MARKER,
            'size_bytes': _content_length(request),
        }

        return payload

    try:
        raw = request.body
    except Exception:                                       # noqa: BLE001
        return payload

    payload['request_body'] = sanitize_body(raw, content_type, limit)

    if payload['request_body'] is None and _is_form(content_type):
        payload['form_fields'] = sanitize(
            {key: request.POST.get(key) for key in request.POST}
        )

    return payload


def _is_form(content_type):
    return content_type.startswith('application/x-www-form-urlencoded')


def _collect_multipart(request):
    """
    Describe a multipart body by its fields and its file metadata.

    Touching `request.POST` here consumes the upload stream, which DRF
    explicitly supports: it falls back to the already-parsed
    `request.POST` / `request.FILES` when the stream is gone. Any failure
    is swallowed, leaving an empty description rather than a broken
    request.
    """
    collected = {
        'form_fields': {},
        'files': [],
        'file_count': 0,
        'total_file_size_bytes': 0,
    }

    try:
        post = request.POST
        files = request.FILES
    except Exception:                                       # noqa: BLE001
        return collected

    collected['form_fields'] = sanitize(
        {key: post.get(key) for key in post}
    )

    total_size = 0

    for field_name in files:
        for uploaded in files.getlist(field_name):
            size = getattr(uploaded, 'size', 0) or 0
            total_size += size
            collected['files'].append({
                'field_name': field_name[:100],
                'filename': (getattr(uploaded, 'name', '') or '')[:255],
                'content_type': (
                    getattr(uploaded, 'content_type', '') or ''
                )[:100],
                'size_bytes': size,
            })

    collected['file_count'] = len(collected['files'])
    collected['total_file_size_bytes'] = total_size

    return collected


_NAMED_GROUP_PATTERN = re.compile(r'\(\?P<(\w+)>[^)]*\)')
_PATH_CONVERTER_PATTERN = re.compile(r'<(?:[^:>]+:)?(\w+)>')


def _resolve_route_pattern(request):
    """
    The matched URL pattern, normalised to `/api/v1/products/{pk}/`.

    Kept alongside the concrete path because the path answers "what
    happened to this one request" while the pattern is what usage,
    performance and error rates aggregate over.
    """
    match = getattr(request, 'resolver_match', None)

    if match is None:
        return ''

    route = getattr(match, 'route', '') or ''

    if not route:
        return ''

    normalized = _NAMED_GROUP_PATTERN.sub(
        lambda found: '{' + found.group(1) + '}', route
    )
    normalized = _PATH_CONVERTER_PATTERN.sub(
        lambda found: '{' + found.group(1) + '}', normalized
    )
    normalized = (
        normalized.replace('^', '').replace('$', '').replace('\\.', '.')
    )

    if not normalized.startswith('/'):
        normalized = '/' + normalized

    return normalized[:255]


def _resolve_status_code(response):
    """
    The status the client actually received.

    An unhandled exception still reaches the client as Django's 500, so
    the response carries the truth whenever there is one.
    """
    return getattr(response, 'status_code', None) or 500


def _response_size(response):
    if response is None or getattr(response, 'streaming', False):
        try:
            return max(int(response['Content-Length']), 0)
        except (TypeError, ValueError, KeyError):
            return 0

    try:
        return len(response.content)
    except Exception:                                       # noqa: BLE001
        return 0


def _collect_response_body(response):
    if response is None or getattr(response, 'streaming', False):
        return None

    try:
        raw = response.content
    except Exception:                                       # noqa: BLE001
        return None

    return sanitize_body(
        raw,
        response.get('Content-Type', ''),
        config.max_response_body_bytes(),
    )


def _duration_ms(monotonic_start):
    if monotonic_start is None:
        return 0

    return max(int((time.monotonic() - monotonic_start) * 1000), 0)


def _resolve_outcome(status_code, exception_info):
    if exception_info is not None:
        return RequestOutcome.EXCEPTION

    if status_code >= 500:
        return RequestOutcome.SERVER_ERROR

    if status_code >= 400:
        return RequestOutcome.CLIENT_ERROR

    return RequestOutcome.SUCCESS


def _collect_error(status_code, response_body, exception_info):
    """
    Record why a request failed.

    An unhandled exception contributes its type and traceback. A handled
    failure contributes what the project's exception handler already put
    in the response body, so a validation error keeps its per-field
    detail. A successful request leaves every error field empty.
    """
    error = {
        'error_message': '',
        'exception_type': '',
        'traceback': '',
        'error_details': None,
    }

    if exception_info is not None:
        exc_type, exc_value, exc_traceback = exception_info
        error['exception_type'] = getattr(
            exc_type, '__name__', str(exc_type)
        )[:255]
        error['error_message'] = str(exc_value)
        error['traceback'] = sanitize_traceback(
            ''.join(
                traceback_module.format_exception(
                    exc_type, exc_value, exc_traceback
                )
            )
        )

    if status_code < 400:
        return error

    if isinstance(response_body, dict):
        message = response_body.get('message') or response_body.get('detail')

        if message and not error['error_message']:
            error['error_message'] = str(message)

        error['error_details'] = response_body.get('errors', response_body)

    return error
