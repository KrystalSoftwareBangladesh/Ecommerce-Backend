from django.db import migrations


# Deterministic technical rules approved by the implementation plan
# (sections 10-14). No keyword or domain rules are seeded: the repository
# defines no suspicious keyword or domain list, and those tables are
# populated by authorised users through the API or the admin.
#
# Severities are graded by execution capability. CRITICAL is reserved for
# rules that mean arbitrary script execution.

HTML_TAG_RULES = [
    ('script', 'INJECTION', 'CRITICAL',
     'Inline or external script element.'),
    ('iframe', 'INJECTION', 'HIGH',
     'Embeds a remote document in the page.'),
    ('object', 'INJECTION', 'HIGH',
     'Embeds external content or a plugin.'),
    ('embed', 'INJECTION', 'HIGH',
     'Embeds external content or a plugin.'),
    ('form', 'PHISHING', 'HIGH',
     'Collects input, commonly used for credential phishing.'),
]

HTML_ATTRIBUTE_RULES = [
    ('onclick', 'ATTRIBUTE', 'INJECTION', 'HIGH',
     'Inline click event handler.'),
    ('onload', 'ATTRIBUTE', 'INJECTION', 'HIGH',
     'Inline load event handler.'),
    ('onerror', 'ATTRIBUTE', 'INJECTION', 'HIGH',
     'Inline error event handler.'),
    ('onmouseover', 'ATTRIBUTE', 'INJECTION', 'HIGH',
     'Inline mouse-over event handler.'),
    ('onfocus', 'ATTRIBUTE', 'INJECTION', 'HIGH',
     'Inline focus event handler.'),
    ('onmouseenter', 'ATTRIBUTE', 'INJECTION', 'HIGH',
     'Inline mouse-enter event handler.'),
    ('javascript:', 'SCHEME', 'INJECTION', 'CRITICAL',
     'Script execution through a URL scheme.'),
    ('data:text/html', 'SCHEME', 'INJECTION', 'CRITICAL',
     'Inline HTML document delivered through a data URL.'),
]

REDIRECT_RULES = [
    ('window.location', 'JAVASCRIPT', 'REDIRECT', 'HIGH',
     'JavaScript navigation away from the page.'),
    ('location.href', 'JAVASCRIPT', 'REDIRECT', 'HIGH',
     'JavaScript navigation away from the page.'),
    ('location.replace', 'JAVASCRIPT', 'REDIRECT', 'HIGH',
     'JavaScript navigation that also rewrites history.'),
    ('location.assign', 'JAVASCRIPT', 'REDIRECT', 'HIGH',
     'JavaScript navigation away from the page.'),
    ('window.open', 'JAVASCRIPT', 'REDIRECT', 'HIGH',
     'JavaScript that opens another document.'),
    ('refresh', 'META_REFRESH', 'REDIRECT', 'HIGH',
     'HTML meta refresh redirect.'),
]

HIDDEN_CONTENT_RULES = [
    ('display:none', 'HIDDEN_CONTENT', 'MEDIUM',
     'Content removed from the layout.'),
    ('visibility:hidden', 'HIDDEN_CONTENT', 'MEDIUM',
     'Content rendered invisible.'),
    ('font-size:0', 'HIDDEN_CONTENT', 'MEDIUM',
     'Text rendered at zero size.'),
    ('left:-9999px', 'HIDDEN_CONTENT', 'MEDIUM',
     'Content positioned off screen.'),
]

# The base64 indicator ships disabled: migrated WordPress content commonly
# carries legitimate data URIs, so an administrator enables it knowingly.
OBFUSCATION_RULES = [
    ('HTML_ENTITY', 'OBFUSCATION', 'HIGH', True, None,
     'Markup or script hidden behind HTML entities.'),
    ('JS_ESCAPE', 'OBFUSCATION', 'HIGH', True, None,
     'Markup hidden behind JavaScript escape sequences.'),
    ('PERCENT_ENCODING', 'OBFUSCATION', 'LOW', True, None,
     'Markup hidden behind percent encoding.'),
    ('BASE64', 'OBFUSCATION', 'MEDIUM', False, 40,
     'Long base64-like run. Disabled by default because legitimate data '
     'URIs match it.'),
]


def seed_rules(apps, schema_editor):
    HtmlTagRule = apps.get_model('content_security_api', 'HtmlTagRule')
    HtmlAttributeRule = apps.get_model(
        'content_security_api', 'HtmlAttributeRule')
    RedirectRule = apps.get_model('content_security_api', 'RedirectRule')
    HiddenContentRule = apps.get_model(
        'content_security_api', 'HiddenContentRule')
    ObfuscationRule = apps.get_model(
        'content_security_api', 'ObfuscationRule')

    for tag, category, severity, description in HTML_TAG_RULES:
        HtmlTagRule.objects.get_or_create(
            tag=tag,
            defaults={
                'category': category,
                'severity': severity,
                'description': description,
            },
        )

    for pattern, pattern_type, category, severity, description in (
        HTML_ATTRIBUTE_RULES
    ):
        HtmlAttributeRule.objects.get_or_create(
            pattern=pattern,
            pattern_type=pattern_type,
            defaults={
                'category': category,
                'severity': severity,
                'description': description,
            },
        )

    for mechanism, mechanism_type, category, severity, description in (
        REDIRECT_RULES
    ):
        RedirectRule.objects.get_or_create(
            mechanism=mechanism,
            mechanism_type=mechanism_type,
            defaults={
                'category': category,
                'severity': severity,
                'description': description,
            },
        )

    for pattern, category, severity, description in HIDDEN_CONTENT_RULES:
        HiddenContentRule.objects.get_or_create(
            pattern=pattern,
            defaults={
                'category': category,
                'severity': severity,
                'description': description,
            },
        )

    for indicator, category, severity, enabled, min_length, description in (
        OBFUSCATION_RULES
    ):
        ObfuscationRule.objects.get_or_create(
            indicator=indicator,
            defaults={
                'category': category,
                'severity': severity,
                'is_enabled': enabled,
                'min_length': min_length,
                'description': description,
            },
        )


def unseed_rules(apps, schema_editor):
    HtmlTagRule = apps.get_model('content_security_api', 'HtmlTagRule')
    HtmlAttributeRule = apps.get_model(
        'content_security_api', 'HtmlAttributeRule')
    RedirectRule = apps.get_model('content_security_api', 'RedirectRule')
    HiddenContentRule = apps.get_model(
        'content_security_api', 'HiddenContentRule')
    ObfuscationRule = apps.get_model(
        'content_security_api', 'ObfuscationRule')

    HtmlTagRule.objects.filter(
        tag__in=[row[0] for row in HTML_TAG_RULES]
    ).delete()
    HtmlAttributeRule.objects.filter(
        pattern__in=[row[0] for row in HTML_ATTRIBUTE_RULES]
    ).delete()
    RedirectRule.objects.filter(
        mechanism__in=[row[0] for row in REDIRECT_RULES]
    ).delete()
    HiddenContentRule.objects.filter(
        pattern__in=[row[0] for row in HIDDEN_CONTENT_RULES]
    ).delete()
    ObfuscationRule.objects.filter(
        indicator__in=[row[0] for row in OBFUSCATION_RULES]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('content_security_api', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_rules, unseed_rules),
    ]
