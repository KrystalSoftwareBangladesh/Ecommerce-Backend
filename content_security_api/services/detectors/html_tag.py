# content_security_api/services/detectors/html_tag.py
from content_security_api.models import DetectorType
from content_security_api.services.detectors.base import (
    BaseDetector,
    findings_from_pattern,
)


class DangerousHTMLDetector(BaseDetector):
    """
    Detects configured dangerous HTML tags.

    Only tags backed by an enabled rule are reported; ordinary markup is
    left alone.
    """
    detector = DetectorType.HTML_TAG

    def detect(self, content, compiled_rules):
        findings = []
        text = content.normalized

        if not text or '<' not in text:
            return findings

        for compiled_rule in compiled_rules:
            findings.extend(
                findings_from_pattern(
                    self.detector,
                    compiled_rule,
                    text,
                    'Dangerous HTML tag detected.',
                    {'tag': compiled_rule.value},
                )
            )

        return findings
