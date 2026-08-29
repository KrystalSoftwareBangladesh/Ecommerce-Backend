# content_security_api/services/rules.py
"""
Loading and compilation of configurable detection rules.

Rules are read from the database once per scan run and their patterns are
compiled once, so scanning thousands of fields never re-queries or
re-compiles. Patterns are always built by this module from a literal rule
value; administrators never supply a regular expression, so there is no
catastrophic-backtracking surface.
"""
import re

from content_security_api.constants import DEFAULT_BASE64_MIN_LENGTH
from content_security_api.models import (
    DomainMatchType,
    DomainRule,
    HiddenContentRule,
    HtmlAttributePatternType,
    HtmlAttributeRule,
    HtmlTagRule,
    KeywordMatchType,
    KeywordRule,
    ObfuscationIndicator,
    ObfuscationRule,
    RedirectMechanismType,
    RedirectRule,
)


OBFUSCATION_PATTERNS = {
    ObfuscationIndicator.HTML_ENTITY: (
        r'&(?:lt|gt|#0*6[02]|#x0*3[ce]);'
    ),
    ObfuscationIndicator.PERCENT_ENCODING: (
        r'%3[ce]'
    ),
    ObfuscationIndicator.JS_ESCAPE: (
        r'\\x3[ce]|\\u003[ce]'
    ),
}


class CompiledRule:
    """
    A stored rule paired with the expression used to evaluate it.
    """

    def __init__(self, rule, value, pattern=None):
        self.rule = rule
        self.value = value
        self.pattern = pattern

    @property
    def rule_id(self):
        return self.rule.pk

    @property
    def category(self):
        return self.rule.category

    @property
    def severity(self):
        return self.rule.severity


class RuleSet:
    """
    Every enabled rule, compiled and grouped by detector.
    """

    def __init__(
        self,
        keywords,
        domains,
        html_tags,
        html_attributes,
        redirects,
        hidden_contents,
        obfuscations,
    ):
        self.keywords = keywords
        self.domains = domains
        self.html_tags = html_tags
        self.html_attributes = html_attributes
        self.redirects = redirects
        self.hidden_contents = hidden_contents
        self.obfuscations = obfuscations


def load_rule_set():
    """
    Read and compile every enabled detection rule.
    """
    return RuleSet(
        keywords=[
            _compile_keyword_rule(rule)
            for rule in _enabled(KeywordRule)
        ],
        domains=[
            CompiledRule(rule, rule.domain.strip().strip('.').lower())
            for rule in _enabled(DomainRule)
        ],
        html_tags=[
            _compile_html_tag_rule(rule)
            for rule in _enabled(HtmlTagRule)
        ],
        html_attributes=[
            _compile_html_attribute_rule(rule)
            for rule in _enabled(HtmlAttributeRule)
        ],
        redirects=[
            _compile_redirect_rule(rule)
            for rule in _enabled(RedirectRule)
        ],
        hidden_contents=[
            _compile_hidden_content_rule(rule)
            for rule in _enabled(HiddenContentRule)
        ],
        obfuscations=[
            compiled
            for compiled in (
                _compile_obfuscation_rule(rule)
                for rule in _enabled(ObfuscationRule)
            )
            if compiled is not None
        ],
    )


def _enabled(model):
    """
    Rules that are enabled, active and not soft deleted.
    """
    return model.objects.filter(
        is_enabled=True,
        is_active=True,
        deleted_at__isnull=True,
    )


def _relax(value, separator):
    """
    Escape a literal value and allow optional whitespace around one
    separator character, so `display:none` also matches `display : none`.
    """
    parts = [re.escape(part.strip()) for part in value.split(separator)]
    joiner = rf'\s*{re.escape(separator)}\s*'

    return joiner.join(parts)


def _compile_keyword_rule(rule):
    keyword = rule.keyword.strip()
    escaped = re.escape(keyword)

    if rule.match_type == KeywordMatchType.WORD:
        expression = rf'\b{escaped}\b'
    else:
        expression = escaped

    return CompiledRule(
        rule,
        keyword,
        re.compile(expression, re.IGNORECASE),
    )


def _compile_html_tag_rule(rule):
    tag = rule.tag.strip().lstrip('<').rstrip('>').lower()

    return CompiledRule(
        rule,
        tag,
        re.compile(rf'<\s*{re.escape(tag)}\b', re.IGNORECASE),
    )


def _compile_html_attribute_rule(rule):
    value = rule.pattern.strip()

    if rule.pattern_type == HtmlAttributePatternType.SCHEME:
        expression = _relax(value, ':')
    else:
        expression = rf'\b{re.escape(value)}\s*='

    return CompiledRule(rule, value, re.compile(expression, re.IGNORECASE))


def _compile_redirect_rule(rule):
    value = rule.mechanism.strip()

    if rule.mechanism_type == RedirectMechanismType.META_REFRESH:
        expression = (
            r'<\s*meta\b[^>]*?http-equiv\s*=\s*["\']?\s*'
            + re.escape(value)
        )
    else:
        expression = rf'\b{_relax(value, ".")}'

    return CompiledRule(rule, value, re.compile(expression, re.IGNORECASE))


def _compile_hidden_content_rule(rule):
    value = rule.pattern.strip()

    return CompiledRule(
        rule,
        value,
        re.compile(rf'\b{_relax(value, ":")}', re.IGNORECASE),
    )


def _compile_obfuscation_rule(rule):
    if rule.indicator == ObfuscationIndicator.BASE64:
        min_length = rule.min_length or DEFAULT_BASE64_MIN_LENGTH
        expression = rf'[A-Za-z0-9+/]{{{min_length},}}={{0,2}}'

        return CompiledRule(
            rule,
            rule.get_indicator_display(),
            re.compile(expression),
        )

    expression = OBFUSCATION_PATTERNS.get(rule.indicator)

    if not expression:
        return None

    return CompiledRule(
        rule,
        rule.get_indicator_display(),
        re.compile(expression, re.IGNORECASE),
    )


def domain_matches(compiled_rule, host):
    """
    Compare an extracted host against a configured domain rule.
    """
    domain = compiled_rule.value

    if not domain or not host:
        return False

    if compiled_rule.rule.match_type == DomainMatchType.EXACT:
        return host == domain

    return host == domain or host.endswith(f'.{domain}')


RULE_TYPES = {
    'keyword_rules': KeywordRule,
    'domain_rules': DomainRule,
    'hidden_content_rules': HiddenContentRule,
    'obfuscation_rules': ObfuscationRule,
    'redirect_rules': RedirectRule,
    'html_attribute_rules': HtmlAttributeRule,
    'html_tag_rules': HtmlTagRule,
}


def count_rules_by_type():
    """
    How many rules are stored for each rule type, plus their total.

    Counting happens in the database, one `COUNT(*)` per rule type; no
    rule is loaded into memory. Disabled (`is_enabled=False`) and
    deactivated (`is_active=False`) rules are counted, because the tab
    badges show how many rules exist, not how many are evaluated. Soft
    deleted rules are left out, so the counts match what the rule list
    endpoints return with no filter applied.
    """
    counts = {
        key: model.objects.filter(deleted_at__isnull=True).count()
        for key, model in RULE_TYPES.items()
    }
    counts['total'] = sum(counts.values())

    return counts
