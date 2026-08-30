# request_log_api/filters.py
import django_filters

from django.db.models import Q

from request_log_api.models import RequestLog


class RequestLogFilter(django_filters.FilterSet):
    """
    Filters for the request log list.

    Covers the identity, network, client, request, response, performance,
    error and time categories the request logging plan calls for. Every
    filter here is backed by an index or by a column narrow enough to scan
    after the indexed filters have done their work.
    """
    # -- Identity ------------------------------------------------------
    anonymous_id = django_filters.CharFilter(
        help_text='Exact client-supplied anonymous identifier',
    )
    request_id = django_filters.CharFilter(
        help_text='Exact correlation identifier',
    )

    # -- Request -------------------------------------------------------
    request_path = django_filters.CharFilter(
        lookup_expr='icontains',
        help_text='Substring of the actual request path',
    )
    route_pattern = django_filters.CharFilter(
        help_text='Exact resolved route pattern',
    )

    # -- Response ------------------------------------------------------
    status_code_min = django_filters.NumberFilter(
        field_name='status_code',
        lookup_expr='gte',
        help_text='Lower bound of the status code range',
    )
    status_code_max = django_filters.NumberFilter(
        field_name='status_code',
        lookup_expr='lte',
        help_text='Upper bound of the status code range',
    )

    # -- Performance ---------------------------------------------------
    min_duration_ms = django_filters.NumberFilter(
        field_name='duration_ms',
        lookup_expr='gte',
        help_text='Slow requests: only those at least this many ms',
    )
    max_duration_ms = django_filters.NumberFilter(
        field_name='duration_ms',
        lookup_expr='lte',
        help_text='Only requests at most this many ms',
    )

    # -- Error ---------------------------------------------------------
    has_error = django_filters.BooleanFilter(
        method='filter_has_error',
        help_text='Whether any error or exception was recorded',
    )
    error_message = django_filters.CharFilter(
        lookup_expr='icontains',
        help_text='Substring of the recorded error message',
    )

    # -- Time ----------------------------------------------------------
    created_after = django_filters.IsoDateTimeFilter(
        field_name='created_at',
        lookup_expr='gte',
        help_text='Only requests logged at or after this timestamp',
    )
    created_before = django_filters.IsoDateTimeFilter(
        field_name='created_at',
        lookup_expr='lte',
        help_text='Only requests logged at or before this timestamp',
    )
    created_date = django_filters.DateFilter(
        field_name='created_at',
        lookup_expr='date',
        help_text='Only requests logged on this date',
    )
    created_hour = django_filters.NumberFilter(
        field_name='created_at',
        lookup_expr='hour',
        help_text='Hour of day, 0-23, in the server time zone',
    )

    class Meta:
        model = RequestLog
        fields = [
            'user',
            'is_authenticated',
            'ip_address',
            'browser',
            'operating_system',
            'device_type',
            'is_mobile',
            'is_bot',
            'bot_name',
            'client_type',
            'origin',
            'frontend_route',
            'request_method',
            'status_code',
            'is_success',
            'outcome',
            'exception_type',
        ]

    def filter_has_error(self, queryset, name, value):
        """
        Split the log on whether anything went wrong.

        An error is either an unhandled exception or a message recorded
        from a failed response, so both columns have to be consulted.
        """
        recorded = Q(exception_type='') & Q(error_message='')

        if value:
            return queryset.exclude(recorded)

        return queryset.filter(recorded)
