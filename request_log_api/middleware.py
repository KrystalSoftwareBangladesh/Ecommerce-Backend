# request_log_api/middleware.py
"""
The one place the request lifecycle is observed.

The middleware times the request, captures its context before the body is
consumed, collects the outcome afterwards, and hands a built event to the
storage layer. It holds no database logic of its own and it never lets a
logging failure reach the caller: every step is wrapped, and the response
is returned unchanged whatever happens here.
"""
import logging
import time

from request_log_api.constants import REQUEST_ID_HEADER
from request_log_api.services import builder
from request_log_api.services.storage import persist_request_log


logger = logging.getLogger(__name__)


class RequestLogMiddleware:
    """
    Creates one immutable `RequestLog` per HTTP request.

    Requests are never deduplicated: ten calls to the same endpoint
    produce ten records.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not self._should_log(request):
            return self.get_response(request)

        monotonic_start = time.monotonic()
        context = self._collect_context(request)

        response = self.get_response(request)

        if context is None:
            return response

        self._stamp_request_id(response, context['request_id'])
        self._log(request, context, response, monotonic_start)

        return response

    def process_exception(self, request, exception):
        """
        Stash an unhandled exception so the response phase can record it.

        Returning None leaves Django's own handling untouched; the
        traceback is read here only because it is no longer reachable by
        the time the converted 500 response comes back.
        """
        try:
            request.request_log_exception = (
                type(exception),
                exception,
                exception.__traceback__,
            )
        except Exception:                                   # noqa: BLE001
            logger.exception('Failed to capture request log exception')

        return None

    def _should_log(self, request):
        try:
            return builder.should_log(request)
        except Exception:                                   # noqa: BLE001
            logger.exception('Failed to evaluate request log filter')

            return False

    def _collect_context(self, request):
        """
        Capture the request half of the record.

        Returning None on failure disables logging for this request only,
        which is why the caller re-checks it before building an event.
        """
        try:
            context = builder.collect_request_context(request)
        except Exception:                                   # noqa: BLE001
            logger.exception('Failed to collect API request context')

            return None

        # Published for correlation: application code and downstream
        # logging can read the same identifier off the request.
        request.request_id = context['request_id']

        return context

    def _stamp_request_id(self, response, request_id):
        try:
            response[REQUEST_ID_HEADER] = request_id
        except Exception:                                   # noqa: BLE001
            logger.exception('Failed to stamp request id on response')

    def _log(self, request, context, response, monotonic_start):
        try:
            event = builder.build_event(
                request,
                context,
                response=response,
                exception_info=getattr(
                    request, 'request_log_exception', None
                ),
                monotonic_start=monotonic_start,
            )
        except Exception:                                   # noqa: BLE001
            logger.exception('Failed to build API request log event')

            return

        persist_request_log(event)
