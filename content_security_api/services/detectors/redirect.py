# content_security_api/services/detectors/redirect.py
from content_security_api.models import DetectorType
from content_security_api.services.detectors.base import (
    BaseDetector,
    findings_from_pattern,
)


class RedirectDetector(BaseDetector):
    """
    Detects configured redirect mechanisms, both JavaScript expressions and
    HTML meta redirects.

    The detector reports only; it never rewrites or removes the redirect.
    """
    detector = DetectorType.REDIRECT

    MESSAGES = {
        'JAVASCRIPT': 'JavaScript redirect mechanism detected.',
        'META_REFRESH': 'HTML meta refresh redirect detected.',
    }

    def detect(self, content, compiled_rules):
        findings = []
        text = content.normalized

        if not text:
            return findings

        for compiled_rule in compiled_rules:
            mechanism_type = compiled_rule.rule.mechanism_type

            findings.extend(
                findings_from_pattern(
                    self.detector,
                    compiled_rule,
                    text,
                    self.MESSAGES.get(
                        mechanism_type,
                        'Redirect mechanism detected.',
                    ),
                    {'mechanism_type': mechanism_type},
                )
            )

        return findings
