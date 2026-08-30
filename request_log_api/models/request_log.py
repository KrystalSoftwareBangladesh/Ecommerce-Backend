# request_log_api/models/request_log.py
from django.db import models

from EcommerceBackend.core.models import TimeStampedModel
from user_api.models import User

from request_log_api.models.choices import (
    ClientType,
    DeviceType,
    RequestOutcome,
)


class RequestLog(TimeStampedModel):
    """
    One immutable record of one HTTP request.

    Rows are written by `request_log_api.middleware.RequestLogMiddleware`
    and are never created, updated or deleted through the API; the ViewSet
    exposes list and retrieve only. Nothing in the application reads a
    request log to make a decision, so the table can be moved to another
    backend later without touching business logic.

    This is not an entity audit log. It answers "who called which API,
    with what, and what happened", not "which field changed from what to
    what".

    Uploaded file contents are never stored - `files` keeps metadata only.
    """
    # -- Identity ------------------------------------------------------
    request_id = models.CharField(
        max_length=64,
        db_index=True,
        help_text=(
            'Correlation identifier, reused from a valid client '
            'X-Request-ID header or generated per request. Not unique: a '
            'client that repeats an identifier produces two records.'
        ),
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='request_logs',
    )
    is_authenticated = models.BooleanField(
        default=False,
        db_index=True,
    )
    anonymous_id = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text='Client-generated X-Anonymous-ID, when supplied.',
    )

    # -- Network -------------------------------------------------------
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            'Client address resolved through the configured trusted '
            'proxy depth.'
        ),
    )
    forwarded_for = models.CharField(
        max_length=255,
        blank=True,
        help_text=(
            'Raw X-Forwarded-For chain, kept as reported and never '
            'trusted on its own.'
        ),
    )

    # -- Client --------------------------------------------------------
    user_agent = models.TextField(
        blank=True,
        help_text=(
            'Raw User-Agent, retained so the parsed fields below can be '
            'recomputed if parsing improves.'
        ),
    )
    browser = models.CharField(max_length=50, blank=True)
    browser_version = models.CharField(max_length=30, blank=True)
    operating_system = models.CharField(max_length=50, blank=True)
    operating_system_version = models.CharField(max_length=30, blank=True)
    device_type = models.CharField(
        max_length=10,
        choices=DeviceType.choices,
        default=DeviceType.UNKNOWN,
    )
    is_mobile = models.BooleanField(default=False)
    is_bot = models.BooleanField(default=False)
    bot_name = models.CharField(max_length=50, blank=True)

    # -- Client source -------------------------------------------------
    client_type = models.CharField(
        max_length=10,
        choices=ClientType.choices,
        default=ClientType.UNKNOWN,
    )
    origin = models.CharField(max_length=255, blank=True)
    referer = models.CharField(max_length=500, blank=True)
    frontend_route = models.CharField(
        max_length=255,
        blank=True,
        help_text='Client-supplied X-Client-Route, when supplied.',
    )

    # -- Request -------------------------------------------------------
    request_method = models.CharField(max_length=10, db_index=True)
    request_path = models.CharField(max_length=500, db_index=True)
    route_pattern = models.CharField(
        max_length=255,
        blank=True,
        help_text=(
            'Resolved URL pattern, e.g. /api/v1/products/{pk}/, for '
            'aggregation across the many concrete paths that share it.'
        ),
    )
    query_parameters = models.JSONField(default=dict, blank=True)
    query_string = models.TextField(blank=True)
    headers = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            'Allow-listed request headers only. Authorization, Cookie '
            'and API key headers are never read.'
        ),
    )
    request_body = models.JSONField(null=True, blank=True)
    is_multipart = models.BooleanField(default=False)
    form_fields = models.JSONField(default=dict, blank=True)
    files = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            'Uploaded file metadata - field name, filename, content type '
            'and size. File contents are never stored.'
        ),
    )
    file_count = models.PositiveSmallIntegerField(default=0)
    total_file_size_bytes = models.PositiveBigIntegerField(default=0)
    request_size_bytes = models.PositiveBigIntegerField(default=0)

    # -- Response ------------------------------------------------------
    status_code = models.PositiveSmallIntegerField()
    response_body = models.JSONField(null=True, blank=True)
    response_size_bytes = models.PositiveBigIntegerField(default=0)

    # -- Performance ---------------------------------------------------
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(default=0, db_index=True)

    # -- Outcome -------------------------------------------------------
    is_success = models.BooleanField(default=True)
    outcome = models.CharField(
        max_length=15,
        choices=RequestOutcome.choices,
        default=RequestOutcome.SUCCESS,
    )

    # -- Error ---------------------------------------------------------
    error_message = models.TextField(blank=True)
    exception_type = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
    )
    traceback = models.TextField(blank=True)
    error_details = models.JSONField(null=True, blank=True)

    class Meta:
        verbose_name = 'API Request Log'
        verbose_name_plural = 'API Request Logs'
        ordering = ['-created_at', '-id']
        permissions = [
            ('view_request_log_request_payload',
             'Can view request log request payload'),
            ('view_request_log_response_payload',
             'Can view request log response payload'),
            ('view_request_log_error_details',
             'Can view request log error details'),
            ('view_request_log_traceback',
             'Can view request log traceback'),
        ]
        # Chosen against the filters and orderings the API actually
        # exposes. The composites lead with the filtered column and end
        # with the default ordering column, so a filtered newest-first
        # page is served by one index. Single-column indexes are declared
        # on the fields themselves; low-cardinality flags such as
        # `is_success` and `is_bot` are deliberately left unindexed.
        indexes = [
            models.Index(fields=['route_pattern', '-created_at']),
            models.Index(fields=['status_code', '-created_at']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['outcome', '-created_at']),
        ]

    def __str__(self):
        return (
            f'{self.request_method} {self.request_path} '
            f'-> {self.status_code}'
        )
