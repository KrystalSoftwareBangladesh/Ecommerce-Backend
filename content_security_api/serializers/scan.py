# content_security_api/serializers/scan.py
from drf_spectacular.utils import extend_schema_field

from rest_framework import serializers

from content_security_api.models import (
    ContentScan,
    ScanContentType,
    ScanType,
)
from content_security_api.serializers.finding import (
    ContentScanFindingDetailSerializer,
)
from content_security_api.services import get_object_label


class ContentScanListSerializer(serializers.ModelSerializer):
    finding_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ContentScan
        fields = [
            'id',
            'content_type',
            'object_id',
            'field_name',
            'status',
            'risk_score',
            'finding_count',
            'scanner_version',
            'scanned_at',
        ]
        read_only_fields = fields


class ContentScanDetailSerializer(serializers.ModelSerializer):
    findings = ContentScanFindingDetailSerializer(many=True, read_only=True)
    object_label = serializers.SerializerMethodField()

    class Meta:
        model = ContentScan
        fields = [
            'id',
            'content_type',
            'object_id',
            'object_label',
            'field_name',
            'status',
            'risk_score',
            'scanner_version',
            'content_hash',
            'scanned_at',
            'created_at',
            'updated_at',
            'findings',
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_object_label(self, obj):
        """
        Name of the scanned object, or an empty string once it is gone.
        """
        return get_object_label(obj.content_type, obj.object_id)


# Which request fields each scan type needs, and which ones it has no
# meaning for. A field with no meaning is rejected rather than ignored, so
# a caller is never left believing a value was honoured.
REQUIRED_FIELDS_BY_SCAN_TYPE = {
    ScanType.OBJECT: ['content_type', 'object_id'],
    ScanType.CONTENT_TYPE: ['content_type'],
    ScanType.ALL: [],
}

UNSUPPORTED_FIELDS_BY_SCAN_TYPE = {
    ScanType.OBJECT: [],
    ScanType.CONTENT_TYPE: ['object_id'],
    ScanType.ALL: ['content_type', 'object_id', 'field_names'],
}


class ContentScanCreateSerializer(serializers.Serializer):
    """
    Request payload for starting a scan.

    `scan_type` selects what the run covers:

    * `OBJECT` (the default) - one object of one content type.
    * `CONTENT_TYPE` - every object of one content type.
    * `ALL` - every content type the scanner supports. The backend owns
      that list, so the caller sends nothing but the scan type.

    Omitting `scan_type` keeps the original single-object contract intact.
    """
    scan_type = serializers.ChoiceField(
        choices=ScanType.choices,
        required=False,
        default=ScanType.OBJECT,
        help_text='Defaults to OBJECT, a scan of one object.',
    )
    content_type = serializers.ChoiceField(
        choices=ScanContentType.choices,
        required=False,
        help_text='Required for OBJECT and CONTENT_TYPE scans.',
    )
    object_id = serializers.IntegerField(
        min_value=1,
        required=False,
        help_text='Required for an OBJECT scan, rejected otherwise.',
    )
    field_names = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
        allow_empty=False,
        help_text=(
            'Optional subset of the content type\'s scannable fields. '
            'All of them are scanned when omitted. Not accepted for an '
            'ALL scan, where the fields differ per content type.'
        ),
    )

    def validate(self, attrs):
        """
        Enforce the fields each scan type requires and forbids.
        """
        scan_type = attrs['scan_type']
        supplied = getattr(self, 'initial_data', {})
        errors = {}

        for field_name in REQUIRED_FIELDS_BY_SCAN_TYPE[scan_type]:
            if attrs.get(field_name) is None:
                errors[field_name] = 'This field is required.'

        for field_name in UNSUPPORTED_FIELDS_BY_SCAN_TYPE[scan_type]:
            if field_name in supplied:
                errors[field_name] = (
                    f'Not accepted when scan_type is {scan_type}.'
                )

        if errors:
            raise serializers.ValidationError(errors)

        return attrs


class ContentScanRunResultSerializer(serializers.Serializer):
    """
    Response shape for a scan run.

    `scans` carries the individual results of an `OBJECT` scan. A
    `CONTENT_TYPE` or `ALL` run reports its counters only and leaves
    `scans` empty; its results are read back through the paginated and
    filterable scan list.
    """
    scanned_objects = serializers.IntegerField(read_only=True)
    scanned_fields = serializers.IntegerField(read_only=True)
    flagged_fields = serializers.IntegerField(read_only=True)
    total_findings = serializers.IntegerField(read_only=True)
    status_counts = serializers.DictField(
        child=serializers.IntegerField(),
        read_only=True,
    )
    scans = ContentScanListSerializer(many=True, read_only=True)
