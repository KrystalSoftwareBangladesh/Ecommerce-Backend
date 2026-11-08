# cms_api/serializers/cms_section.py
"""Serializers for the CMS section API (docs/cms-architecture.md 6).

Input validation lives here: the ``content`` payload is a list of
exactly one Wagtail block (``{"type", "value"}``) whose type must
match ``section_type``. Wagtail block-level errors are flattened into
per-message strings under ``content``.
"""
import json

from django.core.exceptions import (
    ValidationError as DjangoValidationError,
)
from rest_framework import serializers

from cms_api.models import CmsSection
from cms_api.sections import SECTION_TYPES
from cms_api.services import (
    create_section,
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
        return stream


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
    content = SectionContentField(read_only=True)
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
            "archived_at",
            "latest_revision_id",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]


class CmsSectionWriteBaseSerializer(serializers.ModelSerializer):
    content = SectionContentField()

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


class CmsSectionRollbackSerializer(serializers.Serializer):
    revision_id = serializers.IntegerField()


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
