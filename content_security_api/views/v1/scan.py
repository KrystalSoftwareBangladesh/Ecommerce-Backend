# content_security_api/views/v1/scan.py
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema

from django.db.models import Count

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from EcommerceBackend.core.permission import CustomPermissionAccessMixin

from content_security_api.filters import ContentScanFilter
from content_security_api.models import ContentScan
from content_security_api.serializers import (
    ContentScanCreateSerializer,
    ContentScanDetailSerializer,
    ContentScanListSerializer,
    ContentScanRunResultSerializer,
)
from content_security_api.services import (
    get_content_source,
    rescan,
    scan_object,
)


@extend_schema(tags=["Content Security"])
class ContentScanViewSet(
    CustomPermissionAccessMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """
    Scan results, and the endpoint that starts a scan.

    Scan results are never edited or deleted through the API; a re-scan
    replaces them in place.
    """
    permission_classes = [IsAuthenticated]
    custom_permissions = {
        "create": "run_content_scan",
        "rescan": "run_content_scan",
    }
    queryset = ContentScan.objects.all()

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    filterset_class = ContentScanFilter

    search_fields = [
        "field_name",
        "content_type",
    ]
    ordering_fields = [
        "risk_score",
        "scanned_at",
        "id",
    ]
    ordering = ["-risk_score", "-scanned_at"]

    def get_queryset(self):
        queryset = super().get_queryset()

        if self.action == "retrieve":
            return queryset.prefetch_related("findings__reviewed_by")

        if self.action == "list":
            return queryset.annotate(finding_count=Count("findings"))

        return queryset

    def get_serializer_class(self):
        if self.action == "list":
            return ContentScanListSerializer

        if self.action == "create":
            return ContentScanCreateSerializer

        return ContentScanDetailSerializer

    @extend_schema(
        tags=["Content Security"],
        request=ContentScanCreateSerializer,
        responses={201: ContentScanRunResultSerializer},
        description=(
            "Scan one object. Every scannable field of the object is "
            "scanned unless `field_names` narrows it. Scanning a whole "
            "content type is done with the `scan_content` management "
            "command so no HTTP request is held open for it."
        ),
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        content_type = serializer.validated_data["content_type"]
        source = get_content_source(content_type)
        obj = source.get_object(serializer.validated_data["object_id"])

        result = scan_object(
            content_type=content_type,
            obj=obj,
            field_names=serializer.validated_data.get("field_names"),
        )

        return Response(
            _run_result_payload(result, self.get_serializer_context()),
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        tags=["Content Security"],
        request=None,
        responses={200: ContentScanDetailSerializer},
        description=(
            "Re-run the scanner over this scan's target. Use it after "
            "adding or changing detection rules; an earlier clean result "
            "is not assumed to stay valid. Review already recorded on a "
            "finding that reappears unchanged is carried forward."
        ),
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="rescan",
    )
    def rescan(self, request, pk=None):
        scan = self.get_object()

        refreshed = rescan(scan=scan)

        return Response(
            ContentScanDetailSerializer(
                refreshed,
                context=self.get_serializer_context(),
            ).data,
            status=status.HTTP_200_OK,
        )


def _run_result_payload(result, context):
    """
    Shape a `ScanRunResult` for the API.
    """
    return {
        "scanned_objects": result.scanned_objects,
        "scanned_fields": result.scanned_fields,
        "flagged_fields": result.flagged_fields,
        "total_findings": result.total_findings,
        "status_counts": result.status_counts(),
        "scans": ContentScanListSerializer(
            result.scans,
            many=True,
            context=context,
        ).data,
    }
