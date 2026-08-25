# content_security_api/services/detectors/domain.py
from content_security_api.models import DetectorType
from content_security_api.services.detectors.base import DetectorFinding
from content_security_api.services.detectors.base import BaseDetector
from content_security_api.services.rules import domain_matches


class DomainDetector(BaseDetector):
    """
    Compares hosts extracted from the content against configured domain
    rules.

    A host is reported only when it matches a rule. An external domain that
    matches no rule is never a finding, and no network request is made for
    any URL.
    """
    detector = DetectorType.DOMAIN

    def detect(self, content, compiled_rules):
        findings = []

        if not compiled_rules:
            return findings

        hosts = content.hosts

        if not hosts:
            return findings

        for compiled_rule in compiled_rules:
            for host, urls in hosts.items():
                if not domain_matches(compiled_rule, host):
                    continue

                findings.append(
                    DetectorFinding(
                        self.detector,
                        compiled_rule,
                        host,
                        'Suspicious domain detected.',
                        {
                            'occurrences': len(urls),
                            'match_type': compiled_rule.rule.match_type,
                            'urls': urls[:10],
                        },
                    )
                )

        return findings
