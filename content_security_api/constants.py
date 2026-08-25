# content_security_api/constants.py
"""
Central configuration constants for the Content Security Scanner.

`SCANNER_VERSION` is stored on every `ContentScan`. Increment it
deliberately whenever detection behaviour changes, so stale results can be
identified and re-scanned.
"""

SCANNER_VERSION = '1.0'

# Longest matched fragment persisted on a finding. Matches the
# `matched_value` / `rule_value` column width.
MATCHED_VALUE_MAX_LENGTH = 255

# Default run length for the base64-like payload obfuscation indicator.
DEFAULT_BASE64_MIN_LENGTH = 40

# Rows pulled per query when scanning a whole content type.
SCAN_BATCH_SIZE = 500
