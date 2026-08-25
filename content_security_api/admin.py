# content_security_api/admin.py
from django.contrib import admin

from content_security_api.models import (
    ContentScan,
    ContentScanFinding,
    DomainRule,
    HiddenContentRule,
    HtmlAttributeRule,
    HtmlTagRule,
    KeywordRule,
    ObfuscationRule,
    RedirectRule,
)


class DetectionRuleAdmin(admin.ModelAdmin):
    """
    Shared admin behaviour for the configurable rule types.
    """
    list_filter = (
        "category",
        "severity",
        "is_enabled",
        "is_active",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(deleted_at__isnull=True)

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        obj.updated_by = request.user

        super().save_model(request, obj, form, change)


@admin.register(KeywordRule)
class KeywordRuleAdmin(DetectionRuleAdmin):
    list_display = (
        "keyword",
        "match_type",
        "category",
        "severity",
        "is_enabled",
    )
    search_fields = ("keyword", "description")
    list_filter = DetectionRuleAdmin.list_filter + ("match_type",)


@admin.register(DomainRule)
class DomainRuleAdmin(DetectionRuleAdmin):
    list_display = (
        "domain",
        "match_type",
        "category",
        "severity",
        "is_enabled",
    )
    search_fields = ("domain", "description")
    list_filter = DetectionRuleAdmin.list_filter + ("match_type",)


@admin.register(HtmlTagRule)
class HtmlTagRuleAdmin(DetectionRuleAdmin):
    list_display = ("tag", "category", "severity", "is_enabled")
    search_fields = ("tag", "description")


@admin.register(HtmlAttributeRule)
class HtmlAttributeRuleAdmin(DetectionRuleAdmin):
    list_display = (
        "pattern",
        "pattern_type",
        "category",
        "severity",
        "is_enabled",
    )
    search_fields = ("pattern", "description")
    list_filter = DetectionRuleAdmin.list_filter + ("pattern_type",)


@admin.register(RedirectRule)
class RedirectRuleAdmin(DetectionRuleAdmin):
    list_display = (
        "mechanism",
        "mechanism_type",
        "category",
        "severity",
        "is_enabled",
    )
    search_fields = ("mechanism", "description")
    list_filter = DetectionRuleAdmin.list_filter + ("mechanism_type",)


@admin.register(HiddenContentRule)
class HiddenContentRuleAdmin(DetectionRuleAdmin):
    list_display = ("pattern", "category", "severity", "is_enabled")
    search_fields = ("pattern", "description")


@admin.register(ObfuscationRule)
class ObfuscationRuleAdmin(DetectionRuleAdmin):
    list_display = (
        "indicator",
        "min_length",
        "category",
        "severity",
        "is_enabled",
    )
    search_fields = ("description",)
    list_filter = DetectionRuleAdmin.list_filter + ("indicator",)


class ContentScanFindingInline(admin.TabularInline):
    model = ContentScanFinding
    extra = 0
    can_delete = False
    fields = (
        "detector",
        "category",
        "severity",
        "matched_value",
        "review_status",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ContentScan)
class ContentScanAdmin(admin.ModelAdmin):
    list_display = (
        "content_type",
        "object_id",
        "field_name",
        "status",
        "risk_score",
        "scanner_version",
        "scanned_at",
    )
    list_filter = (
        "content_type",
        "status",
        "scanner_version",
    )
    search_fields = ("field_name",)
    ordering = ("-risk_score", "-scanned_at")
    inlines = (ContentScanFindingInline,)
    readonly_fields = (
        "content_type",
        "object_id",
        "field_name",
        "status",
        "risk_score",
        "scanner_version",
        "content_hash",
        "scanned_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        """
        Scans are produced by the scanner, never hand-written.
        """
        return False


@admin.register(ContentScanFinding)
class ContentScanFindingAdmin(admin.ModelAdmin):
    list_display = (
        "scan",
        "detector",
        "category",
        "severity",
        "matched_value",
        "review_status",
        "reviewed_by",
    )
    list_filter = (
        "detector",
        "category",
        "severity",
        "review_status",
    )
    search_fields = ("matched_value", "rule_value", "message")
    readonly_fields = (
        "scan",
        "detector",
        "rule_id_value",
        "rule_value",
        "category",
        "severity",
        "matched_value",
        "message",
        "metadata",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False
