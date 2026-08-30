# request_log_api/services/client.py
"""
Client identification: network address, User-Agent and client type.

The User-Agent parser here is deliberately small and dependency-free. The
project ships no UA parsing library, and adding one is an architectural
change; the raw header is stored on every record precisely so these
derived fields can be recomputed if a parser is introduced later.
"""
import re

from request_log_api.constants import (
    ANONYMOUS_ID_HEADER,
    CLIENT_ROUTE_HEADER,
    CLIENT_TYPE_HEADER,
)
from request_log_api.models.choices import ClientType, DeviceType
from request_log_api.services import config


# CGI names these two without the HTTP_ prefix every other header gets.
_UNPREFIXED_HEADERS = {
    'CONTENT_TYPE': 'CONTENT_TYPE',
    'CONTENT_LENGTH': 'CONTENT_LENGTH',
}


def header_value(request, header):
    """
    Read an HTTP header from the WSGI environ by its wire name.
    """
    normalized = header.upper().replace('-', '_')
    key = _UNPREFIXED_HEADERS.get(normalized, 'HTTP_' + normalized)
    value = request.META.get(key, '')

    return str(value) if value else ''


def resolve_ip_address(request):
    """
    Resolve the client address under the configured trusted proxy depth.

    `X-Forwarded-For` is client-controlled and trivially spoofed, so it is
    trusted only as far as the deployment says it can be: with N trusted
    proxies, the Nth entry from the right is the address the outermost
    trusted proxy observed. With the default of zero, the header is
    recorded but `REMOTE_ADDR` is the client.
    """
    remote_addr = (request.META.get('REMOTE_ADDR') or '').strip()
    proxy_count = config.trusted_proxy_count()

    if proxy_count < 1:
        return remote_addr or None

    forwarded = forwarded_for(request)

    if not forwarded:
        return remote_addr or None

    chain = [part.strip() for part in forwarded.split(',') if part.strip()]

    if len(chain) < proxy_count:
        return remote_addr or None

    return chain[-proxy_count] or remote_addr or None


def forwarded_for(request):
    """
    The raw `X-Forwarded-For` chain, as reported.
    """
    return header_value(request, 'X-Forwarded-For').strip()


def resolve_client_type(request):
    """
    Read the explicit client type header, defaulting to UNKNOWN.
    """
    value = header_value(request, CLIENT_TYPE_HEADER).strip().upper()

    if value in ClientType.values:
        return value

    return ClientType.UNKNOWN


def resolve_anonymous_id(request):
    return header_value(request, ANONYMOUS_ID_HEADER).strip()[:64]


def resolve_frontend_route(request):
    return header_value(request, CLIENT_ROUTE_HEADER).strip()[:255]


# Ordered longest-claim-first: Chrome-derived browsers all carry the
# string "Chrome", and Safari's token appears in nearly every WebKit UA,
# so the specific tokens have to be tested before the general ones.
_BROWSER_PATTERNS = (
    ('Edge', re.compile(r'Edg(?:e|A|iOS)?/([\d.]+)')),
    ('Opera', re.compile(r'OPR/([\d.]+)')),
    ('Opera', re.compile(r'Opera[ /]([\d.]+)')),
    ('Samsung Internet', re.compile(r'SamsungBrowser/([\d.]+)')),
    ('Internet Explorer', re.compile(r'MSIE ([\d.]+)')),
    ('Internet Explorer', re.compile(r'Trident/.*rv:([\d.]+)')),
    ('Firefox', re.compile(r'(?:Firefox|FxiOS)/([\d.]+)')),
    ('Chrome', re.compile(r'(?:Chrome|CriOS)/([\d.]+)')),
    ('Safari', re.compile(r'Version/([\d.]+).*Safari')),
)

_WINDOWS_VERSIONS = {
    '10.0': '10',
    '6.3': '8.1',
    '6.2': '8',
    '6.1': '7',
    '6.0': 'Vista',
    '5.1': 'XP',
}

_OS_PATTERNS = (
    ('Windows', re.compile(r'Windows NT ([\d.]+)')),
    ('Android', re.compile(r'Android ([\d.]+)')),
    ('iOS', re.compile(r'(?:iPhone|iPad|iPod).*?OS ([\d_]+)')),
    ('macOS', re.compile(r'Mac OS X ([\d_.]+)')),
    ('Chrome OS', re.compile(r'CrOS \S+ ([\d.]+)')),
)

_OS_FALLBACKS = (
    ('Windows', 'Windows'),
    ('Android', 'Android'),
    ('Macintosh', 'macOS'),
    ('CrOS', 'Chrome OS'),
    ('Linux', 'Linux'),
)

# Substring -> reported bot name. Matched case-insensitively against the
# raw User-Agent. The generic tokens come last so a named crawler keeps
# its own name.
_BOT_TOKENS = (
    ('googlebot', 'Googlebot'),
    ('bingbot', 'Bingbot'),
    ('yandexbot', 'YandexBot'),
    ('duckduckbot', 'DuckDuckBot'),
    ('baiduspider', 'Baiduspider'),
    ('ahrefsbot', 'AhrefsBot'),
    ('semrushbot', 'SemrushBot'),
    ('facebookexternalhit', 'facebookexternalhit'),
    ('twitterbot', 'Twitterbot'),
    ('slackbot', 'Slackbot'),
    ('telegrambot', 'TelegramBot'),
    ('whatsapp', 'WhatsApp'),
    ('applebot', 'Applebot'),
    ('uptimerobot', 'UptimeRobot'),
    ('pingdom', 'Pingdom'),
    ('headlesschrome', 'HeadlessChrome'),
    ('python-requests', 'python-requests'),
    ('python-httpx', 'python-httpx'),
    ('postmanruntime', 'Postman'),
    ('insomnia', 'Insomnia'),
    ('httpie', 'HTTPie'),
    ('curl/', 'curl'),
    ('wget/', 'Wget'),
    ('crawler', 'Crawler'),
    ('spider', 'Spider'),
    ('bot', 'Bot'),
)

_TABLET_TOKENS = ('ipad', 'tablet', 'kindle', 'playbook', 'silk')


def parse_user_agent(user_agent):
    """
    Derive browser, operating system and device facts from a User-Agent.

    Returns a dict of model field values. An empty or unrecognised header
    yields empty strings and `UNKNOWN`, never a guess.
    """
    raw = (user_agent or '').strip()

    parsed = {
        'browser': '',
        'browser_version': '',
        'operating_system': '',
        'operating_system_version': '',
        'device_type': DeviceType.UNKNOWN,
        'is_mobile': False,
        'is_bot': False,
        'bot_name': '',
    }

    if not raw:
        return parsed

    lowered = raw.lower()

    bot_name = _match_bot(lowered)

    if bot_name:
        parsed['is_bot'] = True
        parsed['bot_name'] = bot_name[:50]
        parsed['device_type'] = DeviceType.BOT

    browser, browser_version = _match_browser(raw)
    parsed['browser'] = browser[:50]
    parsed['browser_version'] = browser_version[:30]

    os_name, os_version = _match_operating_system(raw)
    parsed['operating_system'] = os_name[:50]
    parsed['operating_system_version'] = os_version[:30]

    if not parsed['is_bot']:
        parsed['device_type'] = _match_device_type(lowered)
        parsed['is_mobile'] = parsed['device_type'] == DeviceType.MOBILE

    return parsed


def _match_bot(lowered):
    for token, name in _BOT_TOKENS:
        if token in lowered:
            return name

    return ''


def _match_browser(raw):
    for name, pattern in _BROWSER_PATTERNS:
        match = pattern.search(raw)

        if match:
            return name, match.group(1)

    return '', ''


def _match_operating_system(raw):
    for name, pattern in _OS_PATTERNS:
        match = pattern.search(raw)

        if not match:
            continue

        version = match.group(1).replace('_', '.')

        if name == 'Windows':
            version = _WINDOWS_VERSIONS.get(version, version)

        return name, version

    for token, name in _OS_FALLBACKS:
        if token in raw:
            return name, ''

    return '', ''


def _match_device_type(lowered):
    if any(token in lowered for token in _TABLET_TOKENS):
        return DeviceType.TABLET

    if 'mobi' in lowered or 'iphone' in lowered or 'ipod' in lowered:
        return DeviceType.MOBILE

    if 'android' in lowered:
        return DeviceType.MOBILE

    if not any(
        token in lowered
        for token in ('mozilla', 'opera', 'webkit', 'gecko')
    ):
        return DeviceType.UNKNOWN

    return DeviceType.DESKTOP
