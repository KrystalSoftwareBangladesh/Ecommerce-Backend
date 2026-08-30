# content_security_api/models/choices.py
from django.db import models


class ScanContentType(models.TextChoices):
    """
    Content types the scanner currently supports.

    Adding a new content type is a matter of adding a member here and
    registering it in `content_security_api.services.content_sources`.
    """
    PRODUCT = 'PRODUCT', 'Product'
    CATEGORY = 'CATEGORY', 'Category'


class ScanType(models.TextChoices):
    """
    What one scan request covers.

    `OBJECT` is the default, so a request that names a `content_type` and
    an `object_id` and nothing else keeps the meaning it has always had.
    `ALL` covers every content type registered in
    `content_security_api.services.content_sources`; the caller never
    sends that list.
    """
    OBJECT = 'OBJECT', 'Single Object'
    CONTENT_TYPE = 'CONTENT_TYPE', 'Entire Content Type'
    ALL = 'ALL', 'All Supported Content Types'


class DetectorType(models.TextChoices):
    KEYWORD = 'KEYWORD', 'Keyword'
    DOMAIN = 'DOMAIN', 'Domain'
    HTML_TAG = 'HTML_TAG', 'Dangerous HTML Tag'
    HTML_ATTRIBUTE = 'HTML_ATTRIBUTE', 'Dangerous HTML Attribute'
    REDIRECT = 'REDIRECT', 'Redirect Mechanism'
    HIDDEN_CONTENT = 'HIDDEN_CONTENT', 'Hidden Content'
    OBFUSCATION = 'OBFUSCATION', 'Obfuscation'


class RuleCategory(models.TextChoices):
    GAMBLING = 'GAMBLING', 'Gambling'
    ADULT = 'ADULT', 'Adult'
    DRUG = 'DRUG', 'Drug'
    MALWARE = 'MALWARE', 'Malware'
    SCAM = 'SCAM', 'Scam'
    SPAM = 'SPAM', 'Spam'
    PHISHING = 'PHISHING', 'Phishing'
    REDIRECT = 'REDIRECT', 'Redirect'
    INJECTION = 'INJECTION', 'Injection'
    OBFUSCATION = 'OBFUSCATION', 'Obfuscation'
    HIDDEN_CONTENT = 'HIDDEN_CONTENT', 'Hidden Content'


class RuleSeverity(models.TextChoices):
    INFO = 'INFO', 'Info'
    LOW = 'LOW', 'Low'
    MEDIUM = 'MEDIUM', 'Medium'
    HIGH = 'HIGH', 'High'
    CRITICAL = 'CRITICAL', 'Critical'


class ScanStatus(models.TextChoices):
    CLEAN = 'CLEAN', 'Clean'
    LOW_RISK = 'LOW_RISK', 'Low Risk'
    REVIEW = 'REVIEW', 'Review'
    HIGH_RISK = 'HIGH_RISK', 'High Risk'
    CRITICAL = 'CRITICAL', 'Critical'


class FindingReviewStatus(models.TextChoices):
    """
    Human review state of a single finding.

    PENDING -> FALSE_POSITIVE (terminal)
    PENDING -> CONFIRMED -> RESOLVED

    Review state never changes `ContentScan.risk_score` or
    `ContentScan.status`; those stay pure detection facts.
    """
    PENDING = 'PENDING', 'Pending'
    FALSE_POSITIVE = 'FALSE_POSITIVE', 'False Positive'
    CONFIRMED = 'CONFIRMED', 'Confirmed'
    RESOLVED = 'RESOLVED', 'Resolved'


class KeywordMatchType(models.TextChoices):
    WORD = 'WORD', 'Whole Word'
    SUBSTRING = 'SUBSTRING', 'Substring'


class DomainMatchType(models.TextChoices):
    EXACT = 'EXACT', 'Exact Domain'
    SUBDOMAIN = 'SUBDOMAIN', 'Domain And Subdomains'


class HtmlAttributePatternType(models.TextChoices):
    ATTRIBUTE = 'ATTRIBUTE', 'HTML Attribute'
    SCHEME = 'SCHEME', 'URL Or Script Scheme'


class RedirectMechanismType(models.TextChoices):
    JAVASCRIPT = 'JAVASCRIPT', 'JavaScript Redirect'
    META_REFRESH = 'META_REFRESH', 'HTML Meta Refresh'


class ObfuscationIndicator(models.TextChoices):
    HTML_ENTITY = 'HTML_ENTITY', 'HTML Entity Encoded Markup'
    PERCENT_ENCODING = 'PERCENT_ENCODING', 'Percent Encoded Markup'
    JS_ESCAPE = 'JS_ESCAPE', 'JavaScript Escape Sequence'
    BASE64 = 'BASE64', 'Base64 Like Payload'
