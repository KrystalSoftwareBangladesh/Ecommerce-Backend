# content_security_api/services/normalization.py
"""
Controlled normalization performed once per scanned field.

Each transformation is applied exactly once. There is no decode loop, so a
deeply nested encoding cannot be expanded repeatedly and cannot turn a
single field into unbounded CPU work. Content is never executed, never
written back, and never modified on the source record.

Two views of the content are produced:

    raw         the content exactly as stored, used by the obfuscation
                detector, which needs to see the encoding itself
    normalized  entity decoded, percent decoded and NFKC folded, used by
                every other detector so that encoded evasion still matches
"""
import hashlib
import re
import unicodedata

from html import unescape
from urllib.parse import unquote, urlsplit


URL_PATTERN = re.compile(
    r'(?:https?:)?//[^\s"\'<>()\[\]{}\\]+',
    re.IGNORECASE,
)

ATTRIBUTE_URL_PATTERN = re.compile(
    r'\b(?:href|src|action|data|content)\s*=\s*'
    r'(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+))',
    re.IGNORECASE,
)


class NormalizedContent:
    """
    Result of the normalization pipeline for a single field.
    """

    def __init__(self, raw, normalized, content_hash):
        self.raw = raw
        self.normalized = normalized
        self.content_hash = content_hash
        self._hosts = None

    @property
    def hosts(self):
        """
        Hosts extracted from the normalized content, computed once.
        """
        if self._hosts is None:
            self._hosts = _extract_hosts(self.normalized)
        return self._hosts


def normalize(content):
    """
    Run the normalization pipeline over one field value.
    """
    raw = content or ''

    decoded = unescape(raw)
    decoded = unquote(decoded)
    normalized = unicodedata.normalize('NFKC', decoded)

    content_hash = hashlib.sha256(raw.encode('utf-8')).hexdigest()

    return NormalizedContent(raw, normalized, content_hash)


def _candidate_urls(content):
    """
    Collect URL-like strings from absolute URLs and from URL-bearing HTML
    attribute values.
    """
    candidates = list(URL_PATTERN.findall(content))

    for match in ATTRIBUTE_URL_PATTERN.finditer(content):
        value = match.group(1) or match.group(2) or match.group(3) or ''
        value = value.strip()

        if value:
            candidates.append(value)

    return candidates


def _extract_hosts(content):
    """
    Return an ordered mapping of host -> list of URLs it appeared in.
    """
    hosts = {}

    for candidate in _candidate_urls(content):
        host = _host_of(candidate)

        if not host:
            continue

        urls = hosts.setdefault(host, [])

        if candidate not in urls:
            urls.append(candidate)

    return hosts


def _host_of(candidate):
    """
    Extract a comparable host from a URL-like string.

    Returns an empty string when the candidate carries no host, which is
    the case for relative links and for non-network schemes such as
    `javascript:` or `mailto:`.
    """
    value = candidate.strip()

    if not value:
        return ''

    if value.startswith('//'):
        value = f'http:{value}'
    elif '://' not in value:
        return ''

    try:
        split = urlsplit(value)
    except ValueError:
        return ''

    host = (split.hostname or '').strip().strip('.').lower()

    return host
