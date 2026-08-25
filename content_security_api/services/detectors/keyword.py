# content_security_api/services/detectors/keyword.py
from content_security_api.models import DetectorType
from content_security_api.services.detectors.base import (
    BaseDetector,
    findings_from_pattern,
)


class KeywordDetector(BaseDetector):
    """
    Matches configured keywords and phrases against the normalized content.

    Matching is case insensitive. A WORD rule matches on word boundaries, a
    SUBSTRING rule matches anywhere. Each rule is evaluated once over the
    content and produces at most one finding.
    """
    detector = DetectorType.KEYWORD

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
                    'Suspicious keyword detected.',
                    {'match_type': compiled_rule.rule.match_type},
                )
            )

        return findings
