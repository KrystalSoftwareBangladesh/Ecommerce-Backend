# content_security_api/services/detectors/html_attribute.py
from content_security_api.models import DetectorType
from content_security_api.services.detectors.base import (
    BaseDetector,
    findings_from_pattern,
)


class DangerousAttributeDetector(BaseDetector):
    """
    Detects configured dangerous HTML attributes such as event handlers,
    and configured dangerous URL or script schemes such as `javascript:`.
    """
    detector = DetectorType.HTML_ATTRIBUTE

    MESSAGES = {
        'ATTRIBUTE': 'Dangerous HTML attribute detected.',
        'SCHEME': 'Dangerous URL or script scheme detected.',
    }

    def detect(self, content, compiled_rules):
        findings = []
        text = content.normalized

        if not text:
            return findings

        for compiled_rule in compiled_rules:
            pattern_type = compiled_rule.rule.pattern_type

            findings.extend(
                findings_from_pattern(
                    self.detector,
                    compiled_rule,
                    text,
                    self.MESSAGES.get(
                        pattern_type,
                        'Dangerous HTML attribute detected.',
                    ),
                    {'pattern_type': pattern_type},
                )
            )

        return findings
