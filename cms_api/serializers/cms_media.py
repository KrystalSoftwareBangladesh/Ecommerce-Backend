# cms_api/serializers/cms_media.py
"""CMS media serializers (docs/cms-architecture.md 5.6, 6, 11).

``alt_text`` is exposed as a renamed view of Wagtail's own
``Image.description`` field (not a new column) — see the Phase 4B
audit for why a custom Image model was rejected for just a field
rename. Documents have no description/alt-text equivalent in Wagtail
core.

Likewise the image upload/URL field is exposed as ``image`` (Wagtail's
own ``file`` attribute, renamed to match
``product_api.ProductImage``), so an image resource is always
``image`` + ``alt_text`` on both read and write. Documents keep
``file``, matching the other file-upload APIs in this project.
"""
from rest_framework import serializers

from wagtail.documents.models import Document
from wagtail.images.models import Image

from EcommerceBackend.core.serializers.fields import (
    AbsoluteFileField,
    AbsoluteImageField,
)
from cms_api.models import CmsMediaConfig
from cms_api.services import (
    create_document,
    create_image,
    update_document,
    update_image,
    update_media_config,
)


class CmsMediaConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = CmsMediaConfig
        fields = [
            "max_image_upload_size",
            "max_image_pixels",
            "allowed_image_extensions",
            "max_document_upload_size",
            "allowed_document_extensions",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]

    def update(self, instance, validated_data):
        return update_media_config(
            config=instance,
            validated_data=validated_data,
            user=self.context["request"].user,
        )


class CmsImageListSerializer(serializers.ModelSerializer):
    image = AbsoluteImageField(source="file", read_only=True)
    alt_text = serializers.CharField(source="description", read_only=True)

    class Meta:
        model = Image
        fields = [
            "id",
            "title",
            "alt_text",
            "image",
            "width",
            "height",
            "created_at",
        ]
        read_only_fields = fields


class CmsImageDetailSerializer(CmsImageListSerializer):
    uploaded_by_user = serializers.StringRelatedField(read_only=True)

    class Meta(CmsImageListSerializer.Meta):
        fields = CmsImageListSerializer.Meta.fields + [
            "file_size",
            "uploaded_by_user",
        ]
        read_only_fields = fields


class CmsImageCreateSerializer(serializers.Serializer):
    title = serializers.CharField(
        max_length=255, required=False, allow_blank=True,
    )
    alt_text = serializers.CharField(
        source="description",
        max_length=255,
        required=False,
        allow_blank=True,
    )
    image = serializers.ImageField(source="file")

    def create(self, validated_data):
        return create_image(
            validated_data=validated_data,
            user=self.context["request"].user,
        )


class CmsImageUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(
        max_length=255, required=False, allow_blank=True,
    )
    alt_text = serializers.CharField(
        source="description",
        max_length=255,
        required=False,
        allow_blank=True,
    )
    image = serializers.ImageField(source="file", required=False)

    def update(self, instance, validated_data):
        return update_image(
            image=instance,
            validated_data=validated_data,
            user=self.context["request"].user,
        )


class CmsDocumentListSerializer(serializers.ModelSerializer):
    file = AbsoluteFileField(read_only=True)

    class Meta:
        model = Document
        fields = ["id", "title", "file", "created_at"]
        read_only_fields = fields


class CmsDocumentDetailSerializer(CmsDocumentListSerializer):
    uploaded_by_user = serializers.StringRelatedField(read_only=True)

    class Meta(CmsDocumentListSerializer.Meta):
        fields = CmsDocumentListSerializer.Meta.fields + [
            "file_size",
            "uploaded_by_user",
        ]
        read_only_fields = fields


class CmsDocumentCreateSerializer(serializers.Serializer):
    title = serializers.CharField(
        max_length=255, required=False, allow_blank=True,
    )
    file = serializers.FileField()

    def create(self, validated_data):
        return create_document(
            validated_data=validated_data,
            user=self.context["request"].user,
        )


class CmsDocumentUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(
        max_length=255, required=False, allow_blank=True,
    )
    file = serializers.FileField(required=False)

    def update(self, instance, validated_data):
        return update_document(
            document=instance,
            validated_data=validated_data,
            user=self.context["request"].user,
        )
