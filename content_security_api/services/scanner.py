# content_security_api/services/scanner.py
"""
The scanner service.

    raw content -> normalization -> detectors -> findings
                -> risk calculation -> scan result

`scan_field` is the single entry point every caller goes through: the API,
the `scan_content` management command, and any future automatic or
background scanning. Nothing in this module modifies the content it reads.
"""
from django.db import transaction
from django.utils import timezone

from content_security_api.constants import SCAN_BATCH_SIZE, SCANNER_VERSION
from content_security_api.models import ContentScan, ContentScanFinding
from content_security_api.services.content_sources import (
    CONTENT_SOURCES,
    get_content_source,
    resolve_fields,
)
from content_security_api.services.detectors import (
    DangerousAttributeDetector,
    DangerousHTMLDetector,
    DomainDetector,
    HiddenContentDetector,
    KeywordDetector,
    ObfuscationDetector,
    RedirectDetector,
)
from content_security_api.services.normalization import normalize
from content_security_api.services.rules import load_rule_set
from content_security_api.services.scoring import score, severity_weight


# Detector instances are stateless and reused for the whole process. Each
# entry pairs a detector with the `RuleSet` attribute holding its rules.
DETECTORS = [
    (KeywordDetector(), 'keywords'),
    (DomainDetector(), 'domains'),
    (DangerousHTMLDetector(), 'html_tags'),
    (DangerousAttributeDetector(), 'html_attributes'),
    (RedirectDetector(), 'redirects'),
    (HiddenContentDetector(), 'hidden_contents'),
    (ObfuscationDetector(), 'obfuscations'),
]

REVIEW_FIELDS = [
    'review_status',
    'reviewed_by_id',
    'reviewed_at',
    'review_note',
]


class ScanRunResult:
    """
    Aggregate outcome of a scan run covering one or more fields.
    """

    def __init__(self):
        self.scans = []

    def add(self, scan):
        self.scans.append(scan)

    @property
    def scanned_fields(self):
        return len(self.scans)

    @property
    def scanned_objects(self):
        return len({(scan.content_type, scan.object_id)
                    for scan in self.scans})

    @property
    def flagged_fields(self):
        return len([scan for scan in self.scans if scan.risk_score > 0])

    @property
    def total_findings(self):
        return sum(scan.finding_count for scan in self.scans)

    def status_counts(self):
        counts = {}

        for scan in self.scans:
            counts[scan.status] = counts.get(scan.status, 0) + 1

        return counts


def run_detectors(normalized_content, rule_set):
    """
    Run every detector and return deduplicated findings, worst first.
    """
    findings = []

    for detector, rules_attribute in DETECTORS:
        compiled_rules = getattr(rule_set, rules_attribute)

        if not compiled_rules:
            continue

        findings.extend(detector.detect(normalized_content, compiled_rules))

    return _sort_findings(_dedupe_findings(findings))


@transaction.atomic
def scan_field(
    *,
    content_type,
    object_id,
    field_name,
    content,
    rule_set=None,
    scanner_version=SCANNER_VERSION,
):
    """
    Scan one field of one object and persist the result.

    Returns the stored `ContentScan`, with a `finding_count` attribute set
    to the number of findings written.
    """
    if rule_set is None:
        rule_set = load_rule_set()

    normalized_content = normalize(content)
    findings = run_detectors(normalized_content, rule_set)
    risk_score, status = score(findings)

    scan, _ = ContentScan.objects.update_or_create(
        content_type=content_type,
        object_id=object_id,
        field_name=field_name,
        defaults={
            'status': status,
            'risk_score': risk_score,
            'scanner_version': scanner_version,
            'content_hash': normalized_content.content_hash,
            'scanned_at': timezone.now(),
        },
    )

    previous_reviews = _previous_reviews(scan)

    scan.findings.all().delete()

    ContentScanFinding.objects.bulk_create([
        _build_finding(scan, finding, previous_reviews)
        for finding in findings
    ])

    scan.finding_count = len(findings)

    return scan


def scan_object(*, content_type, obj, field_names=None, rule_set=None):
    """
    Scan every supported field of one already-loaded object.
    """
    source = get_content_source(content_type)
    fields = resolve_fields(source, field_names)

    if rule_set is None:
        rule_set = load_rule_set()

    result = ScanRunResult()

    for field_name in fields:
        result.add(
            scan_field(
                content_type=content_type,
                object_id=obj.pk,
                field_name=field_name,
                content=source.get_content(obj, field_name),
                rule_set=rule_set,
            )
        )

    return result


def scan_content_type(
    *,
    content_type,
    field_names=None,
    rule_set=None,
    batch_size=SCAN_BATCH_SIZE,
    progress=None,
):
    """
    Scan every object of one content type.

    The queryset loads only the identifier, the label and the scanned
    fields, and is streamed in batches so a large migrated catalogue never
    materialises in memory. The rules are loaded and compiled once for the
    whole run.
    """
    source = get_content_source(content_type)
    fields = resolve_fields(source, field_names)

    if rule_set is None:
        rule_set = load_rule_set()

    result = ScanRunResult()

    queryset = source.get_queryset().order_by('pk')

    for obj in queryset.iterator(chunk_size=batch_size):
        for field_name in fields:
            result.add(
                scan_field(
                    content_type=content_type,
                    object_id=obj.pk,
                    field_name=field_name,
                    content=source.get_content(obj, field_name),
                    rule_set=rule_set,
                )
            )

        if progress is not None:
            progress(obj)

    return result


def scan_all(*, rule_set=None, batch_size=SCAN_BATCH_SIZE, progress=None):
    """
    Scan every registered content type.
    """
    if rule_set is None:
        rule_set = load_rule_set()

    result = ScanRunResult()

    for content_type in CONTENT_SOURCES:
        run = scan_content_type(
            content_type=content_type,
            rule_set=rule_set,
            batch_size=batch_size,
            progress=progress,
        )
        result.scans.extend(run.scans)

    return result


def rescan(*, scan, rule_set=None):
    """
    Re-run the scanner over the target of an existing scan.

    Content that scanned clean under an earlier rule set is not assumed to
    be permanently clean; this is how a newly added rule is applied to
    already-scanned content.
    """
    source = get_content_source(scan.content_type)
    obj = source.get_object(scan.object_id)

    return scan_field(
        content_type=scan.content_type,
        object_id=scan.object_id,
        field_name=scan.field_name,
        content=source.get_content(obj, scan.field_name),
        rule_set=rule_set,
    )


def _dedupe_findings(findings):
    """
    Collapse repeats of the same (detector, rule, matched value), summing
    their occurrence counts.
    """
    unique = {}

    for finding in findings:
        existing = unique.get(finding.dedupe_key)

        if existing is None:
            unique[finding.dedupe_key] = finding
            continue

        existing.metadata['occurrences'] = (
            existing.metadata.get('occurrences', 1)
            + finding.metadata.get('occurrences', 1)
        )

    return list(unique.values())


def _sort_findings(findings):
    """
    Order findings by descending severity so the stored rows read worst
    first.
    """
    return sorted(
        findings,
        key=lambda finding: (
            -severity_weight(finding.severity),
            finding.detector,
            finding.matched_value,
        ),
    )


def _previous_reviews(scan):
    """
    Capture the human review state of the current findings, keyed the same
    way findings are deduplicated, so a re-scan does not discard triage.
    """
    previous = {}

    existing = scan.findings.values(
        'detector',
        'rule_id_value',
        'matched_value',
        *REVIEW_FIELDS,
    )

    for row in existing:
        key = (
            row['detector'],
            row['rule_id_value'],
            row['matched_value'],
        )
        previous[key] = {field: row[field] for field in REVIEW_FIELDS}

    return previous


def _build_finding(scan, finding, previous_reviews):
    """
    Build the row for one finding, carrying forward any review already
    recorded for the identical finding.
    """
    review = previous_reviews.get(finding.dedupe_key, {})

    return ContentScanFinding(
        scan=scan,
        detector=finding.detector,
        rule_id_value=finding.rule_id,
        rule_value=finding.rule_value,
        category=finding.category,
        severity=finding.severity,
        matched_value=finding.matched_value,
        message=finding.message,
        metadata=finding.metadata,
        **review,
    )
