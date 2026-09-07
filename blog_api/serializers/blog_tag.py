# blog_api/serializers/blog_tag.py
from rest_framework import serializers

from blog_api.models import BlogTag
from blog_api.services import create_blog_tag, update_blog_tag


class BlogTagSummarySerializer(serializers.ModelSerializer):
    """Compact tag representation nested inside blog post payloads."""

    class Meta:
        model = BlogTag
        fields = [
            'id',
            'name',
            'slug',
        ]


class BlogTagListSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogTag
        fields = [
            'id',
            'name',
            'slug',
            'is_active',
            'created_at',
        ]


class BlogTagDetailSerializer(serializers.ModelSerializer):
    created_by = serializers.StringRelatedField(read_only=True)
    updated_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = BlogTag
        fields = [
            'id',
            'name',
            'slug',
            'legacy_id',
            'is_active',
            'created_at',
            'updated_at',
            'created_by',
            'updated_by',
        ]


class BlogTagCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogTag
        fields = [
            'id',
            'name',
            'slug',
        ]
        read_only_fields = [
            'id',
            'slug',
        ]

    def validate_name(self, value):
        if BlogTag.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError(
                'A blog tag with this name already exists.'
            )
        return value

    def create(self, validated_data):
        return create_blog_tag(
            validated_data=validated_data,
            user=self.context['request'].user,
        )


class BlogTagUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogTag
        fields = [
            'id',
            'name',
            'slug',
        ]
        read_only_fields = [
            'id',
            'slug',
        ]

    def validate_name(self, value):
        qs = BlogTag.objects.filter(name__iexact=value)

        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise serializers.ValidationError(
                'A blog tag with this name already exists.'
            )
        return value

    def update(self, instance, validated_data):
        return update_blog_tag(
            tag=instance,
            validated_data=validated_data,
            user=self.context['request'].user,
        )
