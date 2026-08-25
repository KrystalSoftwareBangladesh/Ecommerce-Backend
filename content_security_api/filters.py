# content_security_api/filters.py
import django_filters

from content_security_api.models import ContentScan, ContentScanFinding


class ContentScanFilter(django_filters.FilterSet):
    """
    Filters for the scan-result list.
    """
    risk_score_min = django_filters.NumberFilter(
        field_name='risk_score',
        lookup_expr='gte',
        help_text='Only scans scoring at least this value',
    )
    risk_score_max = django_filters.NumberFilter(
        field_name='risk_score',
        lookup_expr='lte',
        help_text='Only scans scoring at most this value',
    )
    scanned_after = django_filters.IsoDateTimeFilter(
        field_name='scanned_at',
        lookup_expr='gte',
        help_text='Only scans performed at or after this timestamp',
    )
    scanned_before = django_filters.IsoDateTimeFilter(
        field_name='scanned_at',
        lookup_expr='lte',
        help_text='Only scans performed at or before this timestamp',
    )

    class Meta:
        model = ContentScan
        fields = [
            'content_type',
            'object_id',
            'field_name',
            'status',
            'scanner_version',
        ]


class ContentScanFindingFilter(django_filters.FilterSet):
    """
    Filters for the finding list, including the scan attributes an
    administrator triages by.
    """
    content_type = django_filters.CharFilter(
        field_name='scan__content_type',
        help_text='Content type of the scanned object',
    )
    object_id = django_filters.NumberFilter(
        field_name='scan__object_id',
        help_text='Identifier of the scanned object',
    )
    field_name = django_filters.CharFilter(
        field_name='scan__field_name',
        help_text='Scanned field',
    )
    status = django_filters.CharFilter(
        field_name='scan__status',
        help_text='Overall status of the parent scan',
    )
    rule_id = django_filters.NumberFilter(
        field_name='rule_id_value',
        help_text='Identifier of the rule that produced the finding',
    )

    class Meta:
        model = ContentScanFinding
        fields = [
            'scan',
            'detector',
            'category',
            'severity',
            'review_status',
        ]
