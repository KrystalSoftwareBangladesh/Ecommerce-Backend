# cms_api/serializers/cms_page.py
"""Page and page-composition serializers (docs/cms-architecture.md
5.1, 5.3, 6, 7.1).

Management write serializers call the page services; composition
rows are either written nested (``sections`` on page create/update,
full replace) or one row at a time through the row serializers.
Public serializers render only the published revision (draft
isolation) and resolve global sections to their published content.
"""
from rest_framework import serializers

from cms_api.models import CmsPage, CmsPageSection
from cms_api.models.cms_section import CmsSection
from cms_api.pages.templates import PAGE_TEMPLATE_CHOICES
from cms_api.serializers.cms_section import SectionContentField
from cms_api.services import (
    add_page_section,
    create_page,
    published_url_path,
    update_page,
    update_page_section,
)


class PageSectionContentField(SectionContentField):
    """One-block ``CmsPageSection.content`` payload."""

    model = CmsPageSection


class CmsPageSectionSerializer(serializers.ModelSerializer):
    """Read shape of one composition row (management)."""

    content = PageSectionContentField(read_only=True)

    class Meta:
        model = CmsPageSection
        fields = [
            "id",
            "name",
            "global_section",
            "content",
            "archived_at",
            "sort_order",
        ]
        read_only_fields = fields


class CmsPageSectionWriteSerializer(serializers.Serializer):
    """Write shape of one composition row.

    Exactly one of ``global_section`` or ``content`` must be given
    when a row is created (model XOR rule).
    """

    name = serializers.CharField(
        required=False, allow_blank=True, max_length=255,
    )
    global_section = serializers.PrimaryKeyRelatedField(
        queryset=CmsSection.objects.all(),
        required=False,
        allow_null=True,
    )
    content = PageSectionContentField(required=False, allow_null=True)
    archived = serializers.BooleanField(required=False, default=False)
    base_revision_id = serializers.IntegerField(
        required=False, allow_null=True, write_only=True,
    )

    def validate(self, attrs):
        has_global = attrs.get("global_section") is not None
        has_content = bool(attrs.get("content"))
        both = has_global and has_content
        neither = not has_global and not has_content
        if self.instance is None and (both or neither):
            raise serializers.ValidationError({
                "content": (
                    "Set exactly one of global_section or content."
                )
            })
        if self.instance is not None:
            covers_both = (
                "global_section" in attrs and "content" in attrs
            )
            if covers_both and (both or neither):
                raise serializers.ValidationError({
                    "content": (
                        "Set exactly one of global_section or "
                        "content."
                    )
                })
        return attrs


class CmsPageSectionCreateSerializer(CmsPageSectionWriteSerializer):
    def create(self, validated_data):
        base_revision_id = validated_data.pop("base_revision_id", None)
        return add_page_section(
            page=self.context["page"],
            validated_data=validated_data,
            user=self.context["request"].user,
            base_revision_id=base_revision_id,
        )


class CmsPageSectionUpdateSerializer(CmsPageSectionWriteSerializer):
    def update(self, instance, validated_data):
        base_revision_id = validated_data.pop("base_revision_id", None)
        return update_page_section(
            page=self.context["page"],
            section=instance,
            validated_data=validated_data,
            user=self.context["request"].user,
            base_revision_id=base_revision_id,
        )


class CmsPageSectionReorderSerializer(serializers.Serializer):
    order = serializers.ListField(child=serializers.IntegerField())
    base_revision_id = serializers.IntegerField(
        required=False, allow_null=True, write_only=True,
    )


class CmsPageListSerializer(serializers.ModelSerializer):
    class Meta:
        model = CmsPage
        fields = [
            "id",
            "title",
            "slug",
            "url_path",
            "template_key",
            "live",
            "has_unpublished_changes",
            "archived_at",
            "last_published_at",
        ]
        read_only_fields = fields


class CmsPageDetailSerializer(CmsPageListSerializer):
    sections = CmsPageSectionSerializer(many=True, read_only=True)

    class Meta(CmsPageListSerializer.Meta):
        fields = CmsPageListSerializer.Meta.fields + [
            "draft_title",
            "seo_title",
            "seo_description",
            "meta_keywords",
            "og_title",
            "og_description",
            "og_image",
            "canonical_url",
            "seo_noindex",
            "seo_nofollow",
            "first_published_at",
            "latest_revision_created_at",
            "latest_revision_id",
            "owner",
            "sections",
        ]
        read_only_fields = fields


class CmsPageCreateSerializer(serializers.ModelSerializer):
    parent = serializers.PrimaryKeyRelatedField(
        queryset=CmsPage.objects.all(),
        required=False,
        allow_null=True,
    )
    template_key = serializers.ChoiceField(
        choices=PAGE_TEMPLATE_CHOICES,
        required=False,
    )
    sections = CmsPageSectionWriteSerializer(
        many=True, required=False,
    )

    class Meta:
        model = CmsPage
        fields = [
            "title",
            "slug",
            "parent",
            "template_key",
            "seo_title",
            "seo_description",
            "meta_keywords",
            "og_title",
            "og_description",
            "og_image",
            "canonical_url",
            "seo_noindex",
            "seo_nofollow",
            "sections",
        ]

    def validate(self, attrs):
        if attrs.get("sections") and attrs.get("template_key"):
            raise serializers.ValidationError({
                "sections": (
                    "Provide either template_key or sections, "
                    "not both."
                )
            })
        return attrs

    def create(self, validated_data):
        return create_page(
            validated_data=validated_data,
            user=self.context["request"].user,
        )


class CmsPageUpdateSerializer(serializers.ModelSerializer):
    base_revision_id = serializers.IntegerField(
        required=False, allow_null=True, write_only=True,
    )
    sections = CmsPageSectionWriteSerializer(
        many=True, required=False,
    )

    class Meta:
        model = CmsPage
        fields = [
            "title",
            "slug",
            "seo_title",
            "seo_description",
            "meta_keywords",
            "og_title",
            "og_description",
            "og_image",
            "canonical_url",
            "seo_noindex",
            "seo_nofollow",
            "sections",
            "base_revision_id",
        ]

    def update(self, instance, validated_data):
        base_revision_id = validated_data.pop("base_revision_id", None)
        return update_page(
            page=instance,
            validated_data=validated_data,
            user=self.context["request"].user,
            base_revision_id=base_revision_id,
        )


class CmsPagePublishSerializer(serializers.Serializer):
    revision_id = serializers.IntegerField(
        required=False, allow_null=True,
    )


class CmsPageRollbackSerializer(serializers.Serializer):
    revision_id = serializers.IntegerField()


class CmsPageRevisionSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    user = serializers.StringRelatedField(read_only=True)


def _published_content(section):
    """A global section's published content (live revision)."""
    revision = section.live_revision
    if revision is not None:
        return revision.as_object().content
    return section.content


def _snapshot(value):
    """The published copy of a page (live revision), else the row."""
    revision = value.live_revision
    if revision is not None:
        return revision.as_object()
    return value


def _resolved_rows(value):
    """Resolved composition: global sections to published content.

    Rows whose global section is not published are omitted (draft
    isolation), as are archived rows.
    """
    content_field = PageSectionContentField()
    rows = []
    for row in _snapshot(value).sections.all():
        if row.archived_at is not None:
            continue
        if row.global_section_id:
            section = row.global_section
            if (
                section is None
                or not section.live
                or section.archived_at is not None
            ):
                continue
            body = _published_content(section)
            source = "global"
            global_id = section.pk
        else:
            body = row.content
            source = "local"
            global_id = None
        rows.append({
            "name": row.name,
            "source": source,
            "global_section": global_id,
            "content": (
                content_field.to_representation(body)
                if body is not None else None
            ),
        })
    return rows


class CmsPagePublicListSerializer(serializers.Serializer):
    """Lightweight published-page list (sitemap, navigation)."""

    id = serializers.IntegerField(read_only=True)
    title = serializers.CharField(read_only=True)
    slug = serializers.CharField(read_only=True)
    path = serializers.CharField(source="url_path", read_only=True)
    seo_noindex = serializers.BooleanField(read_only=True)
    lastmod = serializers.DateTimeField(
        source="last_published_at", read_only=True,
    )

    def to_representation(self, instance):
        source = _snapshot(instance)
        return {
            "id": instance.pk,
            "title": source.title,
            "slug": source.slug,
            "path": published_url_path(instance),
            "seo_noindex": source.seo_noindex,
            "lastmod": instance.last_published_at,
        }


class CmsPagePublicDetailSerializer(serializers.Serializer):
    """Published page + resolved composition (draft isolated)."""

    id = serializers.IntegerField(read_only=True)
    title = serializers.CharField(read_only=True)
    slug = serializers.CharField(read_only=True)
    path = serializers.CharField(source="url_path", read_only=True)
    template_key = serializers.CharField(read_only=True)
    seo_title = serializers.CharField(read_only=True)
    seo_description = serializers.CharField(read_only=True)
    meta_keywords = serializers.CharField(read_only=True)
    og_title = serializers.CharField(read_only=True)
    og_description = serializers.CharField(read_only=True)
    og_image = serializers.IntegerField(read_only=True)
    canonical_url = serializers.CharField(read_only=True)
    seo_noindex = serializers.BooleanField(read_only=True)
    seo_nofollow = serializers.BooleanField(read_only=True)
    sections = serializers.SerializerMethodField()

    def get_sections(self, instance):
        return _resolved_rows(instance)

    def to_representation(self, instance):
        source = _snapshot(instance)
        return {
            "id": instance.pk,
            "title": source.title,
            "slug": source.slug,
            "path": published_url_path(instance),
            "template_key": source.template_key,
            "seo_title": source.seo_title,
            "seo_description": source.seo_description,
            "meta_keywords": source.meta_keywords,
            "og_title": source.og_title,
            "og_description": source.og_description,
            "og_image": (
                source.og_image_id if source.og_image_id else None
            ),
            "canonical_url": source.canonical_url,
            "seo_noindex": source.seo_noindex,
            "seo_nofollow": source.seo_nofollow,
            "sections": self.get_sections(instance),
        }
