# content_security_api/services/detectors/base.py
"""
Detector contract.

Every detector receives the normalized content plus the compiled rules for
its own detector type, and returns a list of `DetectorFinding`. Detectors
never touch the database, never modify content and never decide an overall
risk; scoring is the risk scorer's job.
"""
from content_security_api.constants import MATCHED_VALUE_MAX_LENGTH


class DetectorFinding:
    """
    One structured detection.
    """

    def __init__(
        self,
        detector,
        compiled_rule,
        matched_value,
        message,
        metadata=None,
    ):
        self.detector = detector
        self.rule_id = compiled_rule.rule_id
        self.rule_value = truncate(compiled_rule.value)
        self.category = compiled_rule.category
        self.severity = compiled_rule.severity
        self.matched_value = truncate(matched_value)
        self.message = message
        self.metadata = metadata or {}

    @property
    def dedupe_key(self):
        """
        Findings are unique per (detector, rule, matched value) within a
        scan. Repeats of the same match are counted, not re-reported.
        """
        return (self.detector, self.rule_id, self.matched_value)


class BaseDetector:
    detector = None

    def detect(self, content, compiled_rules):
        raise NotImplementedError


def truncate(value):
    """
    Keep a persisted fragment within the column width.
    """
    text = (value or '').strip()

    if len(text) > MATCHED_VALUE_MAX_LENGTH:
        return text[:MATCHED_VALUE_MAX_LENGTH]

    return text


def findings_from_pattern(
    detector,
    compiled_rule,
    text,
    message,
    metadata=None,
):
    """
    Run one compiled rule over one body of text and return at most one
    finding, carrying the occurrence count in its metadata.

    The first match supplies `matched_value` so the admin UI can show what
    actually triggered the rule rather than the rule definition.
    """
    matches = compiled_rule.pattern.findall(text)

    if not matches:
        return []

    first = compiled_rule.pattern.search(text)
    payload = {'occurrences': len(matches)}

    if metadata:
        payload.update(metadata)

    return [
        DetectorFinding(
            detector,
            compiled_rule,
            first.group(0),
            message,
            payload,
        )
    ]
