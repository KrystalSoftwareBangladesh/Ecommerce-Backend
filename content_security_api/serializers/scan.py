# content_security_api/serializers/scan.py
from drf_spectacular.utils import extend_schema_field

from rest_framework import serializers

from content_security_api.models import ContentScan, ScanContentType
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


class ContentScanCreateSerializer(serializers.Serializer):
    """
    Request payload for starting a scan.

    A scan started over HTTP always targets a single object, so the request
    stays bounded. Scanning a whole content type is the `scan_content`
    management command's job.
    """
    content_type = serializers.ChoiceField(
        choices=ScanContentType.choices,
    )
    object_id = serializers.IntegerField(min_value=1)
    field_names = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
        allow_empty=False,
        help_text=(
            'Optional subset of the content type\'s scannable fields. '
            'All of them are scanned when omitted.'
        ),
    )


class ContentScanRunResultSerializer(serializers.Serializer):
    """
    Response shape for a scan run.
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
