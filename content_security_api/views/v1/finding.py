# content_security_api/views/v1/finding.py
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from EcommerceBackend.core.permission import CustomPermissionAccessMixin

from content_security_api.filters import ContentScanFindingFilter
from content_security_api.models import ContentScanFinding
from content_security_api.serializers import (
    ContentScanFindingDetailSerializer,
    ContentScanFindingListSerializer,
    ContentScanFindingResolveSerializer,
    ContentScanFindingReviewSerializer,
)
from content_security_api.services import resolve_finding, review_finding


@extend_schema(tags=["Content Security"])
class ContentScanFindingViewSet(
    CustomPermissionAccessMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    Findings produced by the scanner, and the human review recorded
    against them.

    A finding is a detection, not a verdict. Reviewing one records what a
    person concluded; it never changes the scan's risk score or status, and
    it never modifies the scanned content.
    """
    permission_classes = [IsAuthenticated]
    custom_permissions = {
        "review": "review_content_scan_finding",
        "resolve": "resolve_content_scan_finding",
    }
    queryset = ContentScanFinding.objects.all()

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    filterset_class = ContentScanFindingFilter

    search_fields = [
        "matched_value",
        "rule_value",
        "message",
    ]
    ordering_fields = [
        "created_at",
        "id",
    ]
    ordering = ["scan", "id"]

    def get_queryset(self):
        queryset = super().get_queryset().select_related("scan")

        if self.action in ["retrieve", "review", "resolve"]:
            return queryset.select_related("reviewed_by")

        return queryset

    def get_serializer_class(self):
        if self.action == "list":
            return ContentScanFindingListSerializer

        if self.action == "review":
            return ContentScanFindingReviewSerializer

        if self.action == "resolve":
            return ContentScanFindingResolveSerializer

        return ContentScanFindingDetailSerializer

    @extend_schema(
        tags=["Content Security"],
        request=ContentScanFindingReviewSerializer,
        responses={200: ContentScanFindingDetailSerializer},
        description=(
            "Record a review decision on a pending finding: "
            "FALSE_POSITIVE when the detection is harmless, CONFIRMED "
            "when it is genuinely suspicious."
        ),
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="review",
    )
    def review(self, request, pk=None):
        finding = self.get_object()

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        reviewed = review_finding(
            finding=finding,
            user=request.user,
            review_status=serializer.validated_data["review_status"],
            note=serializer.validated_data.get("review_note", ""),
        )

        return Response(
            ContentScanFindingDetailSerializer(
                reviewed,
                context=self.get_serializer_context(),
            ).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["Content Security"],
        request=ContentScanFindingResolveSerializer,
        responses={200: ContentScanFindingDetailSerializer},
        description=(
            "Mark a confirmed finding as resolved once the content has "
            "been dealt with. The scanner does not change the content "
            "itself."
        ),
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="resolve",
    )
    def resolve(self, request, pk=None):
        finding = self.get_object()

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        resolved = resolve_finding(
            finding=finding,
            user=request.user,
            note=serializer.validated_data.get("review_note", ""),
        )

        return Response(
            ContentScanFindingDetailSerializer(
                resolved,
                context=self.get_serializer_context(),
            ).data,
            status=status.HTTP_200_OK,
        )
