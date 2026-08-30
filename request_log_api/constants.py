# request_log_api/constants.py
"""
Central configuration for API request logging.

Every value here is a default. Each one can be overridden in
`EcommerceBackend/settings.py` (and therefore per deployment) through the
matching `REQUEST_LOG_*` setting, read in
`request_log_api.services.config`.

Nothing in this module imports Django models, so it stays safe to import
from middleware at start-up.
"""

# Headers a client may send to take part in correlation and analytics.
REQUEST_ID_HEADER = 'X-Request-ID'
ANONYMOUS_ID_HEADER = 'X-Anonymous-ID'
CLIENT_TYPE_HEADER = 'X-Client-Type'
CLIENT_ROUTE_HEADER = 'X-Client-Route'

# Request headers worth keeping. Anything not listed here is never read
# into a log record, which is how `Authorization`, `Cookie` and any API key
# header stay out of storage by construction rather than by redaction.
CAPTURED_HEADERS = (
    'Content-Type',
    'Accept',
    'Accept-Language',
    'Origin',
    'Referer',
)

# Paths that never produce a request log. Static and media are served by
# the web server in every deployed environment; logging them locally would
# add noise without adding observability.
EXCLUDED_PATH_PREFIXES = (
    '/static/',
    '/media/',
)

# Bodies are captured only for these content types. An HTML or binary
# response is recorded by its size and status alone, never by its content.
JSON_CONTENT_TYPES = (
    'application/json',
    'application/vnd.api+json',
)
FORM_CONTENT_TYPE = 'application/x-www-form-urlencoded'
MULTIPART_CONTENT_TYPE = 'multipart/form-data'

# Safety limits. A body larger than its limit is replaced by a marker
# rather than truncated, so a stored payload is never a misleading
# fragment of the real one.
MAX_REQUEST_BODY_BYTES = 64 * 1024
MAX_RESPONSE_BODY_BYTES = 256 * 1024
MAX_TRACEBACK_LENGTH = 20000

# Replacement written in place of a body that exceeds its limit.
TRUNCATED_MARKER = '***TRUNCATED***'

# Value written in place of anything sensitive.
REDACTED_MARKER = '***REDACTED***'

# How deep the sanitizer walks before it stops recursing.
MAX_SANITIZE_DEPTH = 12

# Number of proxies in front of the application that may be trusted to
# have appended a client address to `X-Forwarded-For`. Zero means the
# header is recorded but never trusted, and `REMOTE_ADDR` is the client.
TRUSTED_PROXY_COUNT = 0

# Keys whose value is sensitive when the key matches exactly. These are
# short, common names where a substring match would redact innocent keys
# such as `accessible` or `token_count`.
SENSITIVE_EXACT_KEYS = frozenset({
    'access',
    'refresh',
    'token',
    'secret',
    'authorization',
    'cookie',
    'cookies',
    'pin',
    'otp',
    'cvv',
    'cvc',
    'signature',
    'credentials',
})

# Keys whose value is sensitive when the key contains the fragment. This
# is what catches `new_password`, `password_confirmation`, `access_token`,
# `X-Api-Key` and their many spellings without listing each one.
SENSITIVE_KEY_FRAGMENTS = (
    'password',
    'passwd',
    'token',
    'secret',
    'api_key',
    'apikey',
    'api-key',
    'authorization',
    'private_key',
    'card_number',
    'cardnumber',
    'credit_card',
    'security_code',
    'csrf',
    'session_key',
)
