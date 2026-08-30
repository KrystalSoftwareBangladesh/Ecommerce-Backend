# request_log_api/views/v1/request_log.py
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema

from rest_framework import mixins, viewsets
from rest_framework.filters import OrderingFilter, SearchFilter

from EcommerceBackend.core.permission import ModelPermissionAccess

from request_log_api.filters import RequestLogFilter
from request_log_api.models import RequestLog
from request_log_api.serializers import (
    RequestLogDetailSerializer,
    RequestLogListSerializer,
)


@extend_schema(tags=["Request Logs"])
class RequestLogViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    Read-only access to the API request log.

    Records are written by `RequestLogMiddleware`, never by a caller, so
    only list and retrieve exist: create, update and delete are not
    routed at all and answer 405. Access requires the Django
    `view_requestlog` permission; the request and response payloads,
    error details and tracebacks each need their own permission on top of
    that, and are omitted from the detail response without it.
    """
    permission_classes = [ModelPermissionAccess]
    queryset = RequestLog.objects.all()

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    filterset_class = RequestLogFilter

    search_fields = [
        "request_id",
        "request_path",
        "route_pattern",
        "error_message",
        "exception_type",
    ]
    ordering_fields = [
        "created_at",
        "duration_ms",
        "status_code",
        "request_size_bytes",
        "response_size_bytes",
        "id",
    ]
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        return super().get_queryset().select_related("user")

    def get_serializer_class(self):
        if self.action == "list":
            return RequestLogListSerializer

        return RequestLogDetailSerializer
