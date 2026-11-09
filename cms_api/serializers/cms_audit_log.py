# cms_api/serializers/cms_audit_log.py
"""Audit-log serializers (docs/cms-architecture.md §6, §11)."""
from rest_framework import serializers

from cms_api.services.audit_log import CMS_AUDIT_CONTENT_TYPES


class CmsAuditLogQuerySerializer(serializers.Serializer):
    start_date = serializers.DateTimeField(required=False)
    end_date = serializers.DateTimeField(required=False)
    action = serializers.CharField(required=False, allow_blank=False)
    content_type = serializers.ChoiceField(
        choices=sorted(CMS_AUDIT_CONTENT_TYPES),
        required=False,
    )

    def validate(self, attrs):
        start_date = attrs.get("start_date")
        end_date = attrs.get("end_date")
        if (
            start_date is not None
            and end_date is not None
            and start_date > end_date
        ):
            raise serializers.ValidationError({
                "start_date": "start_date must not be after end_date.",
            })
        return attrs


class CmsAuditLogEntrySerializer(serializers.Serializer):
    actor = serializers.CharField(read_only=True, allow_null=True)
    actor_id = serializers.IntegerField(read_only=True, allow_null=True)
    action = serializers.CharField(read_only=True)
    model = serializers.CharField(read_only=True)
    object_id = serializers.CharField(read_only=True, allow_null=True)
    object = serializers.CharField(read_only=True, allow_null=True)
    timestamp = serializers.DateTimeField(read_only=True)
    data = serializers.JSONField(read_only=True)
