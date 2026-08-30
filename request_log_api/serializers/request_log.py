# request_log_api/serializers/request_log.py
from rest_framework import serializers

from user_api.serializers import UserSummarySerializer

from request_log_api.models import RequestLog


# Payload fields a reader sees only when they hold the matching
# permission. Section 39 of the request logging plan: basic access shows
# what happened, technical access shows the contents.
PERMISSION_GATED_FIELDS = {
    'request_body': 'request_log_api.view_request_log_request_payload',
    'form_fields': 'request_log_api.view_request_log_request_payload',
    'response_body': 'request_log_api.view_request_log_response_payload',
    'error_details': 'request_log_api.view_request_log_error_details',
    'traceback': 'request_log_api.view_request_log_traceback',
}


class RequestLogListSerializer(serializers.ModelSerializer):
    """
    Lean row for the request log list.

    Carries no payload at all, so the list stays cheap to read and needs
    no per-field permission checks.
    """
    user = UserSummarySerializer(read_only=True)

    class Meta:
        model = RequestLog
        fields = [
            'id',
            'request_id',
            'user',
            'is_authenticated',
            'anonymous_id',
            'ip_address',
            'client_type',
            'request_method',
            'request_path',
            'route_pattern',
            'status_code',
            'is_success',
            'outcome',
            'duration_ms',
            'request_size_bytes',
            'response_size_bytes',
            'exception_type',
            'created_at',
        ]
        read_only_fields = fields


class RequestLogDetailSerializer(serializers.ModelSerializer):
    """
    Everything recorded about one request, subject to permission.

    A reader without the payload permissions still gets the full technical
    picture - route, timing, status, client - and simply does not see the
    bodies. The fields are omitted rather than blanked so a caller cannot
    mistake a withheld payload for an empty one.
    """
    user = UserSummarySerializer(read_only=True)

    class Meta:
        model = RequestLog
        fields = [
            'id',
            'request_id',
            'user',
            'is_authenticated',
            'anonymous_id',
            'ip_address',
            'forwarded_for',
            'user_agent',
            'browser',
            'browser_version',
            'operating_system',
            'operating_system_version',
            'device_type',
            'is_mobile',
            'is_bot',
            'bot_name',
            'client_type',
            'origin',
            'referer',
            'frontend_route',
            'request_method',
            'request_path',
            'route_pattern',
            'query_parameters',
            'query_string',
            'headers',
            'request_body',
            'is_multipart',
            'form_fields',
            'files',
            'file_count',
            'total_file_size_bytes',
            'request_size_bytes',
            'status_code',
            'response_body',
            'response_size_bytes',
            'started_at',
            'completed_at',
            'duration_ms',
            'is_success',
            'outcome',
            'error_message',
            'exception_type',
            'traceback',
            'error_details',
            'created_at',
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        user = getattr(self.context.get('request'), 'user', None)

        for field, permission in PERMISSION_GATED_FIELDS.items():
            if user is None or not user.has_perm(permission):
                data.pop(field, None)

        return data
