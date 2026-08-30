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
from content_security_api.models import ContentScan, ScanType
from content_security_api.serializers import (
    ContentScanCreateSerializer,
    ContentScanDetailSerializer,
    ContentScanListSerializer,
    ContentScanRunResultSerializer,
)
from content_security_api.services import (
    get_content_source,
    rescan,
    scan_all,
    scan_content_type,
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
            "Start a scan. `scan_type` selects the coverage and defaults "
            "to `OBJECT`.\n\n"
            "* `OBJECT` - one object, named by `content_type` and "
            "`object_id`. Every scannable field is scanned unless "
            "`field_names` narrows it, and the results are embedded in "
            "`scans`.\n"
            "* `CONTENT_TYPE` - every object of the given `content_type`.\n"
            "* `ALL` - every content type the scanner supports. The list "
            "is the backend's; send no other field.\n\n"
            "A `CONTENT_TYPE` or `ALL` run answers with its counters and "
            "an empty `scans`; read the results back from the scan list. "
            "Both run inside the request, so a catalogue large enough to "
            "outlast a request timeout is still the `scan_content` "
            "management command's job."
        ),
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        scan_type = data["scan_type"]

        result = self._run_scan(data)

        return Response(
            _run_result_payload(
                result,
                self.get_serializer_context(),
                include_scans=scan_type == ScanType.OBJECT,
            ),
            status=status.HTTP_201_CREATED,
        )

    def _run_scan(self, data):
        """
        Dispatch a validated request to the matching scanner service.
        """
        scan_type = data["scan_type"]

        if scan_type == ScanType.ALL:
            return scan_all()

        content_type = data["content_type"]
        field_names = data.get("field_names")

        if scan_type == ScanType.CONTENT_TYPE:
            return scan_content_type(
                content_type=content_type,
                field_names=field_names,
            )

        source = get_content_source(content_type)

        return scan_object(
            content_type=content_type,
            obj=source.get_object(data["object_id"]),
            field_names=field_names,
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


def _run_result_payload(result, context, include_scans=True):
    """
    Shape a `ScanRunResult` for the API.

    `include_scans` is off for a bulk run, whose scan rows are unbounded
    and are read back through the paginated scan list instead.
    """
    return {
        "scanned_objects": result.scanned_objects,
        "scanned_fields": result.scanned_fields,
        "flagged_fields": result.flagged_fields,
        "total_findings": result.total_findings,
        "status_counts": result.status_counts(),
        "scans": ContentScanListSerializer(
            result.scans if include_scans else [],
            many=True,
            context=context,
        ).data,
    }
