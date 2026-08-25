# content_security_api/tests/factories.py
"""
Small helpers for building scanner fixtures in tests.

The repository builds fixtures with direct `Model.objects.create(...)`
calls and has no factory library; these are thin wrappers over exactly
that, only to keep the rule-heavy setups readable.
"""
from category_api.models import Category
from product_api.models import Product

from content_security_api.models import (
    DomainRule,
    HiddenContentRule,
    HtmlAttributeRule,
    HtmlTagRule,
    KeywordRule,
    ObfuscationRule,
    RedirectRule,
    RuleCategory,
    RuleSeverity,
)


def keyword_rule(keyword, **kwargs):
    kwargs.setdefault("category", RuleCategory.GAMBLING)
    kwargs.setdefault("severity", RuleSeverity.HIGH)
    return KeywordRule.objects.create(keyword=keyword, **kwargs)


def domain_rule(domain, **kwargs):
    kwargs.setdefault("category", RuleCategory.SPAM)
    kwargs.setdefault("severity", RuleSeverity.MEDIUM)
    return DomainRule.objects.create(domain=domain, **kwargs)


def html_tag_rule(tag, **kwargs):
    kwargs.setdefault("category", RuleCategory.INJECTION)
    kwargs.setdefault("severity", RuleSeverity.CRITICAL)
    return HtmlTagRule.objects.create(tag=tag, **kwargs)


def html_attribute_rule(pattern, **kwargs):
    kwargs.setdefault("category", RuleCategory.INJECTION)
    kwargs.setdefault("severity", RuleSeverity.HIGH)
    return HtmlAttributeRule.objects.create(pattern=pattern, **kwargs)


def redirect_rule(mechanism, **kwargs):
    kwargs.setdefault("category", RuleCategory.REDIRECT)
    kwargs.setdefault("severity", RuleSeverity.HIGH)
    return RedirectRule.objects.create(mechanism=mechanism, **kwargs)


def hidden_content_rule(pattern, **kwargs):
    kwargs.setdefault("category", RuleCategory.HIDDEN_CONTENT)
    kwargs.setdefault("severity", RuleSeverity.MEDIUM)
    return HiddenContentRule.objects.create(pattern=pattern, **kwargs)


def obfuscation_rule(indicator, **kwargs):
    kwargs.setdefault("category", RuleCategory.OBFUSCATION)
    kwargs.setdefault("severity", RuleSeverity.HIGH)
    return ObfuscationRule.objects.create(indicator=indicator, **kwargs)


def clear_seeded_rules():
    """
    Drop the rules installed by the seed migration so a test starts from a
    known rule set.
    """
    for model in [
        KeywordRule,
        DomainRule,
        HtmlTagRule,
        HtmlAttributeRule,
        RedirectRule,
        HiddenContentRule,
        ObfuscationRule,
    ]:
        model.objects.all().delete()


def product(name="Test Product", **kwargs):
    kwargs.setdefault("current_selling_price", "10.00")
    return Product.objects.create(name=name, **kwargs)


def category(name="Test Category", **kwargs):
    return Category.objects.create(name=name, **kwargs)
