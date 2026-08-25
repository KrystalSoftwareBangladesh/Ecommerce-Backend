# content_security_api/models/rule.py
from django.db import models

from EcommerceBackend.core.models import (
    TimeStampedModel, UserStampedModel, SoftDeleteModel
)

from content_security_api.constants import DEFAULT_BASE64_MIN_LENGTH
from content_security_api.models.choices import (
    DomainMatchType,
    HtmlAttributePatternType,
    KeywordMatchType,
    ObfuscationIndicator,
    RedirectMechanismType,
    RuleCategory,
    RuleSeverity,
)


class DetectionRule(TimeStampedModel, UserStampedModel, SoftDeleteModel):
    """
    Shared properties of every configurable detection rule.

    `is_enabled` is the detection toggle an administrator flips to stop a
    rule from being evaluated. It is deliberately separate from the
    `is_active` / `deleted_at` pair inherited from `SoftDeleteModel`, which
    records deletion. A rule is evaluated only when it is enabled, active
    and not soft deleted.
    """
    category = models.CharField(
        max_length=20,
        choices=RuleCategory.choices,
        db_index=True,
    )
    severity = models.CharField(
        max_length=10,
        choices=RuleSeverity.choices,
        db_index=True,
    )
    is_enabled = models.BooleanField(
        default=True,
        db_index=True,
        help_text='Evaluate this rule during a scan',
    )
    description = models.TextField(blank=True)

    class Meta:
        abstract = True


class KeywordRule(DetectionRule):
    keyword = models.CharField(max_length=255)
    match_type = models.CharField(
        max_length=10,
        choices=KeywordMatchType.choices,
        default=KeywordMatchType.WORD,
        help_text=(
            'WORD matches the keyword on word boundaries, '
            'SUBSTRING matches it anywhere. Both are case insensitive.'
        ),
    )

    class Meta:
        verbose_name = 'Keyword Rule'
        verbose_name_plural = 'Keyword Rules'
        ordering = ['keyword']
        indexes = [models.Index(fields=['keyword'])]
        constraints = [
            models.UniqueConstraint(
                fields=['keyword', 'match_type'],
                condition=models.Q(deleted_at__isnull=True),
                name='content_security_unique_active_keyword_rule',
            ),
        ]

    def __str__(self):
        return self.keyword


class DomainRule(DetectionRule):
    domain = models.CharField(max_length=255)
    match_type = models.CharField(
        max_length=10,
        choices=DomainMatchType.choices,
        default=DomainMatchType.SUBDOMAIN,
        help_text=(
            'EXACT matches the host only, SUBDOMAIN also matches any '
            'subdomain of it.'
        ),
    )

    class Meta:
        verbose_name = 'Domain Rule'
        verbose_name_plural = 'Domain Rules'
        ordering = ['domain']
        indexes = [models.Index(fields=['domain'])]
        constraints = [
            models.UniqueConstraint(
                fields=['domain', 'match_type'],
                condition=models.Q(deleted_at__isnull=True),
                name='content_security_unique_active_domain_rule',
            ),
        ]

    def __str__(self):
        return self.domain


class HtmlTagRule(DetectionRule):
    tag = models.CharField(
        max_length=50,
        help_text='HTML tag name without angle brackets, e.g. script',
    )

    class Meta:
        verbose_name = 'HTML Tag Rule'
        verbose_name_plural = 'HTML Tag Rules'
        ordering = ['tag']
        indexes = [models.Index(fields=['tag'])]
        constraints = [
            models.UniqueConstraint(
                fields=['tag'],
                condition=models.Q(deleted_at__isnull=True),
                name='content_security_unique_active_html_tag_rule',
            ),
        ]

    def __str__(self):
        return self.tag


class HtmlAttributeRule(DetectionRule):
    pattern = models.CharField(
        max_length=255,
        help_text=(
            'Attribute name such as onclick, or a scheme such as '
            'javascript: or data:text/html.'
        ),
    )
    pattern_type = models.CharField(
        max_length=15,
        choices=HtmlAttributePatternType.choices,
        default=HtmlAttributePatternType.ATTRIBUTE,
    )

    class Meta:
        verbose_name = 'HTML Attribute Rule'
        verbose_name_plural = 'HTML Attribute Rules'
        ordering = ['pattern']
        indexes = [models.Index(fields=['pattern'])]
        constraints = [
            models.UniqueConstraint(
                fields=['pattern', 'pattern_type'],
                condition=models.Q(deleted_at__isnull=True),
                name='content_security_unique_active_html_attr_rule',
            ),
        ]

    def __str__(self):
        return self.pattern


class RedirectRule(DetectionRule):
    mechanism = models.CharField(
        max_length=255,
        help_text=(
            'JavaScript expression such as window.location, or the '
            'http-equiv value for a meta redirect, such as refresh.'
        ),
    )
    mechanism_type = models.CharField(
        max_length=15,
        choices=RedirectMechanismType.choices,
        default=RedirectMechanismType.JAVASCRIPT,
    )

    class Meta:
        verbose_name = 'Redirect Rule'
        verbose_name_plural = 'Redirect Rules'
        ordering = ['mechanism']
        indexes = [models.Index(fields=['mechanism'])]
        constraints = [
            models.UniqueConstraint(
                fields=['mechanism', 'mechanism_type'],
                condition=models.Q(deleted_at__isnull=True),
                name='content_security_unique_active_redirect_rule',
            ),
        ]

    def __str__(self):
        return self.mechanism


class HiddenContentRule(DetectionRule):
    pattern = models.CharField(
        max_length=255,
        help_text=(
            'CSS declaration such as display:none. Whitespace around the '
            'colon is tolerated when matching.'
        ),
    )

    class Meta:
        verbose_name = 'Hidden Content Rule'
        verbose_name_plural = 'Hidden Content Rules'
        ordering = ['pattern']
        indexes = [models.Index(fields=['pattern'])]
        constraints = [
            models.UniqueConstraint(
                fields=['pattern'],
                condition=models.Q(deleted_at__isnull=True),
                name='content_security_unique_active_hidden_rule',
            ),
        ]

    def __str__(self):
        return self.pattern


class ObfuscationRule(DetectionRule):
    """
    Obfuscation rules select a structural encoding indicator rather than
    carrying a free-form pattern. The detection expressions are properties
    of an encoding, not blacklist data, so administrators configure which
    indicators are evaluated and how they are graded rather than authoring
    the expressions themselves.
    """
    indicator = models.CharField(
        max_length=20,
        choices=ObfuscationIndicator.choices,
    )
    min_length = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        default=DEFAULT_BASE64_MIN_LENGTH,
        help_text=(
            'Minimum run length. Used by the BASE64 indicator only and '
            'ignored by every other indicator.'
        ),
    )

    class Meta:
        verbose_name = 'Obfuscation Rule'
        verbose_name_plural = 'Obfuscation Rules'
        ordering = ['indicator']
        constraints = [
            models.UniqueConstraint(
                fields=['indicator'],
                condition=models.Q(deleted_at__isnull=True),
                name='content_security_unique_active_obfuscation_rule',
            ),
        ]

    def __str__(self):
        return self.get_indicator_display()
