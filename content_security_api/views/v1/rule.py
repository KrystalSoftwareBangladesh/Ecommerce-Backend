# content_security_api/views/v1/rule.py
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema

from rest_framework import status, viewsets
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from EcommerceBackend.core.permission import ModelPermissionAccess

from content_security_api.models import (
    DomainRule,
    HiddenContentRule,
    HtmlAttributeRule,
    HtmlTagRule,
    KeywordRule,
    ObfuscationRule,
    RedirectRule,
)
from content_security_api.serializers import (
    DetectionRuleSummarySerializer,
    DomainRuleCreateUpdateSerializer,
    DomainRuleDetailSerializer,
    DomainRuleListSerializer,
    HiddenContentRuleCreateUpdateSerializer,
    HiddenContentRuleDetailSerializer,
    HiddenContentRuleListSerializer,
    HtmlAttributeRuleCreateUpdateSerializer,
    HtmlAttributeRuleDetailSerializer,
    HtmlAttributeRuleListSerializer,
    HtmlTagRuleCreateUpdateSerializer,
    HtmlTagRuleDetailSerializer,
    HtmlTagRuleListSerializer,
    KeywordRuleCreateUpdateSerializer,
    KeywordRuleDetailSerializer,
    KeywordRuleListSerializer,
    ObfuscationRuleCreateUpdateSerializer,
    ObfuscationRuleDetailSerializer,
    ObfuscationRuleListSerializer,
    RedirectRuleCreateUpdateSerializer,
    RedirectRuleDetailSerializer,
    RedirectRuleListSerializer,
)
from content_security_api.services import count_rules_by_type


class BaseDetectionRuleViewSet(viewsets.ModelViewSet):
    """
    Shared CRUD behaviour for every configurable rule type.

    Rule management is driven entirely by Django model permissions, so a
    role can be given control of one rule type without being given control
    of the others.
    """
    permission_classes = [ModelPermissionAccess]

    list_serializer_class = None
    detail_serializer_class = None
    write_serializer_class = None

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    filterset_fields = [
        "category",
        "severity",
        "is_enabled",
        "is_active",
    ]

    search_fields = ["description"]
    ordering_fields = ["created_at", "id"]

    def get_serializer_class(self):
        if self.action == "list":
            return self.list_serializer_class

        if self.action == "retrieve":
            return self.detail_serializer_class

        return self.write_serializer_class

    def perform_create(self, serializer):
        serializer.save(
            created_by=self.request.user,
            updated_by=self.request.user,
        )

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        instance.updated_by = request.user
        instance.save(update_fields=["updated_by", "updated_at"])

        instance.soft_delete()

        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Content Security - Rules"])
class KeywordRuleViewSet(BaseDetectionRuleViewSet):
    queryset = KeywordRule.objects.filter(deleted_at__isnull=True)
    list_serializer_class = KeywordRuleListSerializer
    detail_serializer_class = KeywordRuleDetailSerializer
    write_serializer_class = KeywordRuleCreateUpdateSerializer
    search_fields = ["keyword", "description"]
    ordering_fields = ["keyword", "created_at", "id"]
    ordering = ["keyword"]
    filterset_fields = BaseDetectionRuleViewSet.filterset_fields + [
        "match_type",
    ]


@extend_schema(tags=["Content Security - Rules"])
class DomainRuleViewSet(BaseDetectionRuleViewSet):
    queryset = DomainRule.objects.filter(deleted_at__isnull=True)
    list_serializer_class = DomainRuleListSerializer
    detail_serializer_class = DomainRuleDetailSerializer
    write_serializer_class = DomainRuleCreateUpdateSerializer
    search_fields = ["domain", "description"]
    ordering_fields = ["domain", "created_at", "id"]
    ordering = ["domain"]
    filterset_fields = BaseDetectionRuleViewSet.filterset_fields + [
        "match_type",
    ]


@extend_schema(tags=["Content Security - Rules"])
class HtmlTagRuleViewSet(BaseDetectionRuleViewSet):
    queryset = HtmlTagRule.objects.filter(deleted_at__isnull=True)
    list_serializer_class = HtmlTagRuleListSerializer
    detail_serializer_class = HtmlTagRuleDetailSerializer
    write_serializer_class = HtmlTagRuleCreateUpdateSerializer
    search_fields = ["tag", "description"]
    ordering_fields = ["tag", "created_at", "id"]
    ordering = ["tag"]


@extend_schema(tags=["Content Security - Rules"])
class HtmlAttributeRuleViewSet(BaseDetectionRuleViewSet):
    queryset = HtmlAttributeRule.objects.filter(deleted_at__isnull=True)
    list_serializer_class = HtmlAttributeRuleListSerializer
    detail_serializer_class = HtmlAttributeRuleDetailSerializer
    write_serializer_class = HtmlAttributeRuleCreateUpdateSerializer
    search_fields = ["pattern", "description"]
    ordering_fields = ["pattern", "created_at", "id"]
    ordering = ["pattern"]
    filterset_fields = BaseDetectionRuleViewSet.filterset_fields + [
        "pattern_type",
    ]


@extend_schema(tags=["Content Security - Rules"])
class RedirectRuleViewSet(BaseDetectionRuleViewSet):
    queryset = RedirectRule.objects.filter(deleted_at__isnull=True)
    list_serializer_class = RedirectRuleListSerializer
    detail_serializer_class = RedirectRuleDetailSerializer
    write_serializer_class = RedirectRuleCreateUpdateSerializer
    search_fields = ["mechanism", "description"]
    ordering_fields = ["mechanism", "created_at", "id"]
    ordering = ["mechanism"]
    filterset_fields = BaseDetectionRuleViewSet.filterset_fields + [
        "mechanism_type",
    ]


@extend_schema(tags=["Content Security - Rules"])
class HiddenContentRuleViewSet(BaseDetectionRuleViewSet):
    queryset = HiddenContentRule.objects.filter(deleted_at__isnull=True)
    list_serializer_class = HiddenContentRuleListSerializer
    detail_serializer_class = HiddenContentRuleDetailSerializer
    write_serializer_class = HiddenContentRuleCreateUpdateSerializer
    search_fields = ["pattern", "description"]
    ordering_fields = ["pattern", "created_at", "id"]
    ordering = ["pattern"]


@extend_schema(tags=["Content Security - Rules"])
class ObfuscationRuleViewSet(BaseDetectionRuleViewSet):
    queryset = ObfuscationRule.objects.filter(deleted_at__isnull=True)
    list_serializer_class = ObfuscationRuleListSerializer
    detail_serializer_class = ObfuscationRuleDetailSerializer
    write_serializer_class = ObfuscationRuleCreateUpdateSerializer
    search_fields = ["description"]
    ordering_fields = ["indicator", "created_at", "id"]
    ordering = ["indicator"]
    filterset_fields = BaseDetectionRuleViewSet.filterset_fields + [
        "indicator",
    ]


@extend_schema(
    tags=["Content Security - Rules"],
    summary="Detection rule summary",
    responses={200: DetectionRuleSummarySerializer},
    description=(
        "How many rules exist for each rule type, for the count badges "
        "beside the Detection Rules tabs. Disabled and deactivated rules "
        "are counted; the list endpoints' search, filter, ordering and "
        "pagination parameters are not applied."
    ),
)
class DetectionRuleSummaryAPIView(APIView):
    """
    Rule counts only. No rule object is ever returned here.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = DetectionRuleSummarySerializer(count_rules_by_type())

        return Response(serializer.data, status=status.HTTP_200_OK)
