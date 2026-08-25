# content_security_api/services/detectors/obfuscation.py
from content_security_api.models import DetectorType
from content_security_api.services.detectors.base import (
    BaseDetector,
    findings_from_pattern,
)


class ObfuscationDetector(BaseDetector):
    """
    Detects encoding used to hide markup or script.

    This detector reads the raw content rather than the normalized content,
    because normalization removes the very encoding it looks for. It only
    reports that an encoding is present; it never decodes recursively and
    never evaluates what the encoding contains.
    """
    detector = DetectorType.OBFUSCATION

    MESSAGES = {
        'HTML_ENTITY': 'HTML entity encoded markup detected.',
        'PERCENT_ENCODING': 'Percent encoded markup detected.',
        'JS_ESCAPE': 'JavaScript escape sequence for markup detected.',
        'BASE64': 'Base64 like payload detected.',
    }

    def detect(self, content, compiled_rules):
        findings = []
        text = content.raw

        if not text:
            return findings

        for compiled_rule in compiled_rules:
            indicator = compiled_rule.rule.indicator

            findings.extend(
                findings_from_pattern(
                    self.detector,
                    compiled_rule,
                    text,
                    self.MESSAGES.get(
                        indicator,
                        'Obfuscated content detected.',
                    ),
                    {'indicator': indicator},
                )
            )

        return findings
