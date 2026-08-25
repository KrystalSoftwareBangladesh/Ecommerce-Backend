# content_security_api/tests/test_detectors.py
from django.test import TestCase

from content_security_api.models import (
    DomainMatchType,
    HtmlAttributePatternType,
    KeywordMatchType,
    ObfuscationIndicator,
    RedirectMechanismType,
)
from content_security_api.services import load_rule_set, normalize
from content_security_api.services.detectors import (
    DangerousAttributeDetector,
    DangerousHTMLDetector,
    DomainDetector,
    HiddenContentDetector,
    KeywordDetector,
    ObfuscationDetector,
    RedirectDetector,
)
from content_security_api.tests import factories


class DetectorTestCase(TestCase):
    """
    Every detector test starts from an empty rule set so only the rules the
    test declares are in play.
    """
    rules_attribute = None
    detector_class = None

    def setUp(self):
        factories.clear_seeded_rules()

    def detect(self, content):
        rule_set = load_rule_set()
        detector = self.detector_class()

        return detector.detect(
            normalize(content),
            getattr(rule_set, self.rules_attribute),
        )


class KeywordDetectorTests(DetectorTestCase):
    rules_attribute = "keywords"
    detector_class = KeywordDetector

    def test_matching_keyword_is_reported(self):
        rule = factories.keyword_rule("casino")

        findings = self.detect("Visit our casino today.")

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].matched_value, "casino")
        self.assertEqual(findings[0].rule_id, rule.pk)
        self.assertEqual(findings[0].severity, rule.severity)

    def test_absent_keyword_is_not_reported(self):
        factories.keyword_rule("casino")

        self.assertEqual(self.detect("A perfectly normal product."), [])

    def test_matching_is_case_insensitive(self):
        factories.keyword_rule("casino")

        findings = self.detect("CASINO night")

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].matched_value, "CASINO")

    def test_word_match_does_not_match_inside_another_word(self):
        factories.keyword_rule("bet", match_type=KeywordMatchType.WORD)

        self.assertEqual(self.detect("A better keyboard."), [])

    def test_substring_match_matches_inside_another_word(self):
        factories.keyword_rule(
            "bet",
            match_type=KeywordMatchType.SUBSTRING,
        )

        findings = self.detect("A better keyboard.")

        self.assertEqual(len(findings), 1)

    def test_multiple_rules_produce_multiple_findings(self):
        factories.keyword_rule("casino")
        factories.keyword_rule("poker")

        findings = self.detect("casino and poker")

        self.assertEqual(len(findings), 2)

    def test_repeats_of_one_keyword_are_counted_not_duplicated(self):
        factories.keyword_rule("casino")

        findings = self.detect("casino casino casino")

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].metadata["occurrences"], 3)

    def test_disabled_rule_is_ignored(self):
        factories.keyword_rule("casino", is_enabled=False)

        self.assertEqual(self.detect("Visit our casino today."), [])

    def test_soft_deleted_rule_is_ignored(self):
        rule = factories.keyword_rule("casino")
        rule.soft_delete()

        self.assertEqual(self.detect("Visit our casino today."), [])

    def test_phrase_rule_matches_a_phrase(self):
        factories.keyword_rule("online casino bonus")

        findings = self.detect("Claim your online casino bonus now.")

        self.assertEqual(len(findings), 1)


class DomainDetectorTests(DetectorTestCase):
    rules_attribute = "domains"
    detector_class = DomainDetector

    def test_matching_domain_is_reported(self):
        factories.domain_rule("bad-example.com")

        findings = self.detect('<a href="https://bad-example.com/x">go</a>')

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].matched_value, "bad-example.com")

    def test_unlisted_domain_is_not_reported(self):
        factories.domain_rule("bad-example.com")

        self.assertEqual(
            self.detect('<a href="https://good-example.com">go</a>'),
            [],
        )

    def test_external_domains_are_not_suspicious_without_a_rule(self):
        self.assertEqual(
            self.detect("Read more at https://en.wikipedia.org/wiki/X"),
            [],
        )

    def test_subdomain_rule_matches_a_subdomain(self):
        factories.domain_rule(
            "bad-example.com",
            match_type=DomainMatchType.SUBDOMAIN,
        )

        findings = self.detect("https://promo.bad-example.com/offer")

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].matched_value, "promo.bad-example.com")

    def test_exact_rule_does_not_match_a_subdomain(self):
        factories.domain_rule(
            "bad-example.com",
            match_type=DomainMatchType.EXACT,
        )

        self.assertEqual(
            self.detect("https://promo.bad-example.com/offer"),
            [],
        )

    def test_subdomain_rule_does_not_match_a_lookalike_suffix(self):
        factories.domain_rule("example.com")

        self.assertEqual(self.detect("https://notexample.com/x"), [])

    def test_plain_url_without_markup_is_scanned(self):
        factories.domain_rule("bad-example.com")

        findings = self.detect("Go to https://bad-example.com/path now")

        self.assertEqual(len(findings), 1)

    def test_multiple_urls_on_one_host_produce_one_finding(self):
        factories.domain_rule("bad-example.com")

        findings = self.detect(
            "https://bad-example.com/a and https://bad-example.com/b"
        )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].metadata["occurrences"], 2)

    def test_disabled_rule_is_ignored(self):
        factories.domain_rule("bad-example.com", is_enabled=False)

        self.assertEqual(
            self.detect("https://bad-example.com/x"),
            [],
        )


class DangerousHTMLDetectorTests(DetectorTestCase):
    rules_attribute = "html_tags"
    detector_class = DangerousHTMLDetector

    def test_dangerous_tag_is_reported(self):
        factories.html_tag_rule("script")

        findings = self.detect('<script>alert(1)</script>')

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_value, "script")

    def test_safe_tag_is_not_reported(self):
        factories.html_tag_rule("script")

        self.assertEqual(self.detect("<p>Hello <b>world</b></p>"), [])

    def test_multiple_dangerous_tags_are_reported(self):
        factories.html_tag_rule("script")
        factories.html_tag_rule("iframe", severity="HIGH")

        findings = self.detect('<script></script><iframe src="x"></iframe>')

        self.assertEqual(len(findings), 2)

    def test_whitespace_inside_the_tag_still_matches(self):
        factories.html_tag_rule("script")

        self.assertEqual(len(self.detect("< script >x</script>")), 1)

    def test_disabled_rule_is_ignored(self):
        factories.html_tag_rule("script", is_enabled=False)

        self.assertEqual(self.detect("<script></script>"), [])


class DangerousAttributeDetectorTests(DetectorTestCase):
    rules_attribute = "html_attributes"
    detector_class = DangerousAttributeDetector

    def test_dangerous_attribute_is_reported(self):
        factories.html_attribute_rule("onerror")

        findings = self.detect('<img src="x" onerror="steal()">')

        self.assertEqual(len(findings), 1)

    def test_safe_attribute_is_not_reported(self):
        factories.html_attribute_rule("onerror")

        self.assertEqual(
            self.detect('<img src="x" alt="A product photo">'),
            [],
        )

    def test_javascript_scheme_is_reported(self):
        factories.html_attribute_rule(
            "javascript:",
            pattern_type=HtmlAttributePatternType.SCHEME,
            severity="CRITICAL",
        )

        findings = self.detect('<a href="javascript:alert(1)">x</a>')

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "CRITICAL")

    def test_data_text_html_scheme_is_reported(self):
        factories.html_attribute_rule(
            "data:text/html",
            pattern_type=HtmlAttributePatternType.SCHEME,
            severity="CRITICAL",
        )

        findings = self.detect(
            '<iframe src="data:text/html;base64,PHA+"></iframe>'
        )

        self.assertEqual(len(findings), 1)

    def test_attribute_name_inside_prose_is_not_reported(self):
        factories.html_attribute_rule("onclick")

        self.assertEqual(
            self.detect("The onclick handler is documented in the manual."),
            [],
        )

    def test_disabled_rule_is_ignored(self):
        factories.html_attribute_rule("onerror", is_enabled=False)

        self.assertEqual(self.detect('<img onerror="x">'), [])


class RedirectDetectorTests(DetectorTestCase):
    rules_attribute = "redirects"
    detector_class = RedirectDetector

    def test_javascript_redirect_is_reported(self):
        factories.redirect_rule("window.location")

        findings = self.detect(
            "<script>window.location = 'https://x.test'</script>"
        )

        self.assertEqual(len(findings), 1)

    def test_location_replace_is_reported(self):
        factories.redirect_rule("location.replace")

        findings = self.detect("location.replace('https://x.test')")

        self.assertEqual(len(findings), 1)

    def test_meta_refresh_is_reported(self):
        factories.redirect_rule(
            "refresh",
            mechanism_type=RedirectMechanismType.META_REFRESH,
        )

        findings = self.detect(
            '<meta http-equiv="refresh" content="0;url=https://x.test">'
        )

        self.assertEqual(len(findings), 1)

    def test_safe_content_is_not_reported(self):
        factories.redirect_rule("window.location")
        factories.redirect_rule(
            "refresh",
            mechanism_type=RedirectMechanismType.META_REFRESH,
        )

        self.assertEqual(
            self.detect("<p>Refresh the page to see the new price.</p>"),
            [],
        )

    def test_disabled_rule_is_ignored(self):
        factories.redirect_rule("window.location", is_enabled=False)

        self.assertEqual(self.detect("window.location='x'"), [])


class HiddenContentDetectorTests(DetectorTestCase):
    rules_attribute = "hidden_contents"
    detector_class = HiddenContentDetector

    def test_configured_hidden_pattern_is_reported(self):
        factories.hidden_content_rule("display:none")

        findings = self.detect('<div style="display:none">spam</div>')

        self.assertEqual(len(findings), 1)

    def test_whitespace_in_the_declaration_still_matches(self):
        factories.hidden_content_rule("display:none")

        findings = self.detect('<div style="display: none">spam</div>')

        self.assertEqual(len(findings), 1)

    def test_off_screen_positioning_is_reported(self):
        factories.hidden_content_rule("left:-9999px")

        findings = self.detect('<div style="left:-9999px">spam</div>')

        self.assertEqual(len(findings), 1)

    def test_safe_content_is_not_reported(self):
        factories.hidden_content_rule("display:none")
        factories.hidden_content_rule("visibility:hidden")

        self.assertEqual(
            self.detect('<div style="display:flex">Specs</div>'),
            [],
        )

    def test_disabled_rule_is_ignored(self):
        factories.hidden_content_rule("display:none", is_enabled=False)

        self.assertEqual(self.detect('<div style="display:none">'), [])


class ObfuscationDetectorTests(DetectorTestCase):
    rules_attribute = "obfuscations"
    detector_class = ObfuscationDetector

    def test_html_entity_encoded_markup_is_reported(self):
        factories.obfuscation_rule(ObfuscationIndicator.HTML_ENTITY)

        findings = self.detect("&lt;script&gt;alert(1)&lt;/script&gt;")

        self.assertGreaterEqual(len(findings), 1)

    def test_numeric_entity_encoded_markup_is_reported(self):
        factories.obfuscation_rule(ObfuscationIndicator.HTML_ENTITY)

        self.assertEqual(len(self.detect("&#60;script&#62;")), 1)

    def test_percent_encoded_markup_is_reported(self):
        factories.obfuscation_rule(
            ObfuscationIndicator.PERCENT_ENCODING,
            severity="LOW",
        )

        self.assertEqual(len(self.detect("%3Cscript%3E")), 1)

    def test_javascript_escape_sequence_is_reported(self):
        factories.obfuscation_rule(ObfuscationIndicator.JS_ESCAPE)

        self.assertEqual(len(self.detect("\\x3cscript\\x3e")), 1)

    def test_base64_like_run_is_reported_when_enabled(self):
        factories.obfuscation_rule(
            ObfuscationIndicator.BASE64,
            severity="MEDIUM",
            min_length=40,
        )

        payload = "QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVphYmNkZWZnaGlqaw=="

        self.assertEqual(len(self.detect(payload)), 1)

    def test_short_alphanumeric_runs_are_not_base64_findings(self):
        factories.obfuscation_rule(
            ObfuscationIndicator.BASE64,
            severity="MEDIUM",
            min_length=40,
        )

        self.assertEqual(self.detect("Model ABC123 in stock"), [])

    def test_ordinary_content_is_not_reported(self):
        factories.obfuscation_rule(ObfuscationIndicator.HTML_ENTITY)
        factories.obfuscation_rule(
            ObfuscationIndicator.PERCENT_ENCODING,
            severity="LOW",
        )

        content = "<p>Weight &amp; size: 2kg. See https://x.test/a%20b</p>"

        self.assertEqual(self.detect(content), [])

    def test_disabled_rule_is_ignored(self):
        factories.obfuscation_rule(
            ObfuscationIndicator.HTML_ENTITY,
            is_enabled=False,
        )

        self.assertEqual(self.detect("&lt;script&gt;"), [])
