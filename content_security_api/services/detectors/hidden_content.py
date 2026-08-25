# content_security_api/services/detectors/hidden_content.py
from content_security_api.models import DetectorType
from content_security_api.services.detectors.base import (
    BaseDetector,
    findings_from_pattern,
)


class HiddenContentDetector(BaseDetector):
    """
    Detects configured hidden-content patterns.

    Hidden content is reported as a finding for human assessment. It is not
    treated as proof of malicious content on its own.
    """
    detector = DetectorType.HIDDEN_CONTENT

    def detect(self, content, compiled_rules):
        findings = []
        text = content.normalized

        if not text:
            return findings

        for compiled_rule in compiled_rules:
            findings.extend(
                findings_from_pattern(
                    self.detector,
                    compiled_rule,
                    text,
                    'Hidden content pattern detected.',
                    {'pattern': compiled_rule.value},
                )
            )

        return findings
