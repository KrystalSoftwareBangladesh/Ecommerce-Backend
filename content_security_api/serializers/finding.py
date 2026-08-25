# content_security_api/serializers/finding.py
from rest_framework import serializers

from content_security_api.models import (
    ContentScanFinding,
    FindingReviewStatus,
)


class ContentScanFindingListSerializer(serializers.ModelSerializer):
    content_type = serializers.CharField(
        source='scan.content_type',
        read_only=True,
    )
    object_id = serializers.IntegerField(
        source='scan.object_id',
        read_only=True,
    )
    field_name = serializers.CharField(
        source='scan.field_name',
        read_only=True,
    )

    class Meta:
        model = ContentScanFinding
        fields = [
            'id',
            'scan',
            'content_type',
            'object_id',
            'field_name',
            'detector',
            'category',
            'severity',
            'rule_value',
            'matched_value',
            'message',
            'review_status',
            'created_at',
        ]
        read_only_fields = fields


class ContentScanFindingDetailSerializer(serializers.ModelSerializer):
    content_type = serializers.CharField(
        source='scan.content_type',
        read_only=True,
    )
    object_id = serializers.IntegerField(
        source='scan.object_id',
        read_only=True,
    )
    field_name = serializers.CharField(
        source='scan.field_name',
        read_only=True,
    )
    reviewed_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = ContentScanFinding
        fields = [
            'id',
            'scan',
            'content_type',
            'object_id',
            'field_name',
            'detector',
            'rule_id_value',
            'rule_value',
            'category',
            'severity',
            'matched_value',
            'message',
            'metadata',
            'review_status',
            'reviewed_by',
            'reviewed_at',
            'review_note',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields


class ContentScanFindingReviewSerializer(serializers.Serializer):
    """
    Request payload for recording a review decision on a finding.
    """
    review_status = serializers.ChoiceField(
        choices=[
            FindingReviewStatus.FALSE_POSITIVE,
            FindingReviewStatus.CONFIRMED,
        ],
        help_text=(
            'FALSE_POSITIVE marks the detection as harmless, CONFIRMED '
            'marks it as genuinely suspicious.'
        ),
    )
    review_note = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=2000,
    )


class ContentScanFindingResolveSerializer(serializers.Serializer):
    """
    Request payload for resolving a confirmed finding.
    """
    review_note = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=2000,
    )
