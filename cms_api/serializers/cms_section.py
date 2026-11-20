# cms_api/serializers/cms_section.py
"""Serializers for the CMS section API (docs/cms-architecture.md 6).

Input validation lives here: the ``content`` payload is a list of
exactly one Wagtail block (``{"type", "value"}``) whose type must
match ``section_type``. Wagtail block-level errors are flattened into
per-message strings under ``content``.
"""
import json
import re

from django.core.exceptions import (
    ValidationError as DjangoValidationError,
)
from django.utils.html import escape

from drf_spectacular.utils import extend_schema_field

from rest_framework import serializers

from wagtail.blocks import ListBlock, RichTextBlock, StreamBlock, StructBlock
from wagtail.models import Page
from wagtail.rich_text import expand_db_html
from wagtail.rich_text.rewriters import FIND_A_TAG, extract_attrs

from cms_api.models import CmsSection
from cms_api.sections import SECTION_TYPE_CHOICES, SECTION_TYPES
from cms_api.services import (
    create_section,
    published_url_path,
    update_section,
)


def _flatten_wagtail_error(error, prefix=""):
    """Flatten Wagtail block validation errors to message strings."""
    messages = []
    block_errors = getattr(error, "block_errors", None)
    non_block_errors = getattr(error, "non_block_errors", None)
    if block_errors:
        for key, sub in block_errors.items():
            path = "%s.%s" % (prefix, key) if prefix else str(key)
            messages.extend(_flatten_wagtail_error(sub, path))
    if non_block_errors:
        for sub in non_block_errors.as_data():
            messages.extend(_flatten_wagtail_error(sub, prefix))
    if not block_errors and non_block_errors is None:
        for msg in error.messages:
            messages.append("%s: %s" % (prefix, msg) if prefix else msg)
    return messages


class SectionContentField(serializers.Field):
    """The one-block StreamField payload.

    Accepts a list of exactly one ``{"type", "value"}`` object; returns
    Wagtail's API representation of the stream.
    """

    model = CmsSection

    default_error_messages = {
        "invalid": "Content must be a list of block objects.",
        "not_single_block": (
            "Content must contain exactly one section block."
        ),
        "invalid_item": (
            "Each block must be an object with 'type' and 'value'."
        ),
        "unknown_type": "Unknown section block type.",
    }

    def to_representation(self, value):
        if value is None:
            return []
        model_field = self.model._meta.get_field("content")
        return model_field.stream_block.get_api_representation(value)

    def to_internal_value(self, data):
        if not isinstance(data, list):
            self.fail("invalid")
        if len(data) != 1:
            self.fail("not_single_block")
        item = data[0]
        if (
            not isinstance(item, dict)
            or "type" not in item
            or "value" not in item
        ):
            self.fail("invalid_item")
        if item["type"] not in SECTION_TYPES:
            self.fail("unknown_type")
        model_field = self.model._meta.get_field("content")
        try:
            stream = model_field.to_python(json.dumps(data))
        except (KeyError, TypeError, ValueError):
            self.fail("invalid")
        try:
            model_field.stream_block.clean(stream)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                _flatten_wagtail_error(exc)
            )
        except (TypeError, ValueError):
            # A chooser field (image/category/brand/product) was given
            # a value Wagtail doesn't treat as "empty", e.g. "" instead
            # of null, which reaches a PK lookup unvalidated.
            raise serializers.ValidationError(
                "Content contains an invalid reference value."
            )
        return stream


_EMBED_PLACEHOLDER = re.compile(
    r"<(?:embed|img)\b"
    r'([^>]*?(?<![\w-])embedtype="[^"]+"[^>]*?)\s*/?>'
)


def _expand_page_links(html):
    """Resolve ``linktype="page"`` links to published public URLs.

    Wagtail's own page-link expansion resolves through ``Page.url``
    and ``Site.root_page``, which yields no URL for any page in this
    project and would embed draft (unpublished) slugs. The public API's
    own ``path`` — ``published_url_path``, built from live-revision
    slugs — is the canonical published URL. A link whose page no longer
    exists becomes a bare ``<a>`` (Wagtail's own fallback).
    """
    found = [
        (match, extract_attrs(match.group(1)))
        for match in FIND_A_TAG.finditer(html)
    ]
    ids = [
        attrs.get("id") for _, attrs in found
        if attrs.get("linktype") == "page"
        and (attrs.get("id") or "").isdigit()
    ]
    pages = {
        str(page.pk): page
        for page in Page.objects.filter(pk__in=ids).select_related(
            "live_revision",
        )
    }

    def replace(match):
        attrs = extract_attrs(match.group(1))
        if attrs.get("linktype") != "page":
            return match.group(0)
        page = pages.get(str(attrs.get("id")))
        if page is None:
            return "<a>"
        return '<a href="%s">' % escape(published_url_path(page))

    return FIND_A_TAG.sub(replace, html)


def expand_rich_text(html):
    """Expand one rich text value's database HTML to usable HTML.

    Wagtail's ``expand_db_html`` resolves embeds (images to rendition
    ``<img>`` tags) and document/external links. Two project-specific
    passes run first: page links resolve to ``published_url_path``
    (draft-isolated), and image placeholders are normalised to
    Wagtail's canonical ``<embed ... />`` form so either stored
    spelling expands.
    """
    html = _EMBED_PLACEHOLDER.sub(
        lambda match: "<embed%s />" % match.group(1), html,
    )
    return expand_db_html(_expand_page_links(html))


def expand_stream_rich_text(block, api_repr):
    """Expand rich text placeholders in a stream's API representation.

    Wagtail stores rich text as database HTML (``linktype``/``embedtype``
    placeholders); ``expand_rich_text`` resolves them to usable URLs.
    Walks stream/struct/list blocks and expands every rich text value,
    leaving all other values untouched.
    """
    if isinstance(block, RichTextBlock):
        return expand_rich_text(api_repr) if api_repr else api_repr
    if isinstance(block, StreamBlock):
        return [
            {
                "type": item["type"],
                "value": expand_stream_rich_text(
                    block.child_blocks[item["type"]], item["value"],
                ),
            }
            for item in api_repr
        ]
    if isinstance(block, ListBlock):
        return [
            expand_stream_rich_text(block.child_block, item)
            for item in api_repr
        ]
    if isinstance(block, StructBlock):
        return {
            key: (
                expand_stream_rich_text(block.child_blocks[key], val)
                if key in block.child_blocks else val
            )
            for key, val in api_repr.items()
        }
    return api_repr


class ExpandedSectionContentField(SectionContentField):
    """``SectionContentField`` with rich text expanded to usable URLs.

    Public and preview responses only: management reads keep raw
    database HTML so a read-modify-write round-trip never stores
    expanded URLs in place of tracked links.
    """

    def to_representation(self, value):
        api_repr = super().to_representation(value)
        model_field = self.model._meta.get_field("content")
        return expand_stream_rich_text(
            model_field.stream_block, api_repr
        )


class SectionBlockSerializer(serializers.Serializer):
    """One entry of a ``content`` list: a single Wagtail block."""

    type = serializers.CharField()
    value = serializers.JSONField()


@extend_schema_field(serializers.ListField(
    child=SectionBlockSerializer(),
    help_text="Exactly one section block.",
))
class SectionContentSchemaField(SectionContentField):
    """``SectionContentField`` typed as the block list it accepts."""


class CmsSectionListSerializer(serializers.ModelSerializer):
    class Meta:
        model = CmsSection
        fields = [
            "id",
            "name",
            "section_type",
            "live",
            "has_unpublished_changes",
            "archived_at",
            "updated_at",
        ]


class CmsSectionDetailSerializer(serializers.ModelSerializer):
    content = SectionContentSchemaField(read_only=True)
    created_by = serializers.StringRelatedField(read_only=True)
    updated_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = CmsSection
        fields = [
            "id",
            "name",
            "section_type",
            "content",
            "live",
            "has_unpublished_changes",
            "first_published_at",
            "last_published_at",
            "go_live_at",
            "expire_at",
            "expired",
            "archived_at",
            "latest_revision_id",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]


class CmsSectionWriteBaseSerializer(serializers.ModelSerializer):
    content = SectionContentSchemaField()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        section_type = attrs.get(
            "section_type",
            getattr(self.instance, "section_type", None),
        )
        content = attrs.get("content")
        if content is not None and section_type:
            stream = list(content)
            if stream and stream[0].block_type != section_type:
                raise serializers.ValidationError({
                    "content": (
                        "Content block type must match section_type "
                        "(%s)." % section_type
                    ),
                })
        return attrs


class CmsSectionCreateSerializer(CmsSectionWriteBaseSerializer):
    class Meta:
        model = CmsSection
        fields = ["name", "section_type", "content"]

    def create(self, validated_data):
        return create_section(
            validated_data=validated_data,
            user=self.context["request"].user,
        )


class _SectionContentBlockSchemaSerializer(serializers.Serializer):
    """Documents one ``{"type", "value"}`` block (schema only)."""

    type = serializers.ChoiceField(choices=SECTION_TYPE_CHOICES)
    value = serializers.DictField(
        help_text=(
            "Fields for this block type. See GET "
            "/api/v1/cms/section-types/ for each type's schema."
        ),
    )


class CmsSectionCreateRequestSchemaSerializer(serializers.Serializer):
    """Request schema for ``POST /api/v1/cms/sections/`` (docs only).

    ``CmsSectionCreateSerializer`` still does the real validation; this
    exists only so Swagger/OpenAPI shows ``content`` as a one-item list
    of ``{"type", "value"}`` blocks instead of a bare string.
    """

    name = serializers.CharField()
    section_type = serializers.ChoiceField(choices=SECTION_TYPE_CHOICES)
    content = _SectionContentBlockSchemaSerializer(many=True)


class CmsSectionUpdateSerializer(CmsSectionWriteBaseSerializer):
    base_revision_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        write_only=True,
    )

    class Meta:
        model = CmsSection
        fields = ["name", "content", "base_revision_id"]

    def update(self, instance, validated_data):
        base_revision_id = validated_data.pop("base_revision_id", None)
        return update_section(
            section=instance,
            validated_data=validated_data,
            user=self.context["request"].user,
            base_revision_id=base_revision_id,
        )


class CmsSectionRevisionSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    user = serializers.StringRelatedField(read_only=True)


class CmsSectionPublishSerializer(serializers.Serializer):
    revision_id = serializers.IntegerField(
        required=False,
        allow_null=True,
    )
    go_live_at = serializers.DateTimeField(
        required=False, allow_null=True,
    )
    expire_at = serializers.DateTimeField(
        required=False, allow_null=True,
    )

    def validate(self, attrs):
        if attrs.get("revision_id") is not None and (
            attrs.get("go_live_at") is not None
            or attrs.get("expire_at") is not None
        ):
            raise serializers.ValidationError({
                "revision_id": (
                    "Cannot combine revision_id with go_live_at/"
                    "expire_at."
                ),
            })
        return attrs


class CmsSectionRollbackSerializer(serializers.Serializer):
    revision_id = serializers.IntegerField()


class CmsSectionPreviewTokenSerializer(serializers.Serializer):
    revision_id = serializers.IntegerField(
        required=False, allow_null=True,
    )


class CmsSectionPreviewTokenResponseSerializer(serializers.Serializer):
    token = serializers.CharField(read_only=True)
    revision_id = serializers.IntegerField(read_only=True)
    expires_in = serializers.IntegerField(read_only=True)


class CmsSectionPreviewSerializer(serializers.Serializer):
    """A previewed section revision's content (AD-15)."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    section_type = serializers.CharField(read_only=True)
    content = ExpandedSectionContentField(read_only=True)


class SectionTypeSchemaSerializer(serializers.Serializer):
    type = serializers.CharField(read_only=True)
    label = serializers.CharField(read_only=True)
    content = serializers.JSONField(read_only=True)


class CmsSectionReferenceSerializer(serializers.Serializer):
    model = serializers.CharField(allow_null=True, read_only=True)
    object_id = serializers.CharField(read_only=True)
    object = serializers.CharField(allow_null=True, read_only=True)
    fields = serializers.ListField(
        child=serializers.CharField(),
        read_only=True,
    )
