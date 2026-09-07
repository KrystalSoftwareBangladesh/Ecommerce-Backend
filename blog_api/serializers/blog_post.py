# blog_api/serializers/blog_post.py
from rest_framework import serializers

from EcommerceBackend.core.serializers.fields import AbsoluteImageField

from category_api.models import Category
from category_api.serializers import CategorySummarySerializer
from user_api.serializers import UserSummarySerializer

from blog_api.models import BlogPost, BlogTag
from blog_api.services import create_blog_post, update_blog_post

from .blog_tag import BlogTagSummarySerializer


CATEGORY_QUERYSET = Category.objects.filter(
    is_active=True,
    deleted_at__isnull=True,
)
TAG_QUERYSET = BlogTag.objects.filter(
    is_active=True,
    deleted_at__isnull=True,
)


class BlogPostListSerializer(serializers.ModelSerializer):
    author = UserSummarySerializer(read_only=True)
    categories = CategorySummarySerializer(many=True, read_only=True)
    tags = BlogTagSummarySerializer(many=True, read_only=True)
    featured_image = AbsoluteImageField(read_only=True)

    class Meta:
        model = BlogPost
        fields = [
            'id',
            'title',
            'slug',
            'author',
            'status',
            'published_at',
            'featured_image',
            'featured_image_alt_text',
            'categories',
            'tags',
            'created_at',
        ]


class BlogPostDetailSerializer(serializers.ModelSerializer):
    author = UserSummarySerializer(read_only=True)
    categories = CategorySummarySerializer(many=True, read_only=True)
    tags = BlogTagSummarySerializer(many=True, read_only=True)
    featured_image = AbsoluteImageField(read_only=True)
    created_by = serializers.StringRelatedField(read_only=True)
    updated_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = BlogPost
        fields = [
            'id',
            'title',
            'slug',
            'content',
            'author',
            'status',
            'published_at',
            'featured_image',
            'featured_image_alt_text',
            'categories',
            'tags',
            'seo_title',
            'seo_description',
            'seo_focus_keyword',
            'seo_noindex',
            'seo_nofollow',
            'legacy_id',
            'is_active',
            'created_at',
            'updated_at',
            'created_by',
            'updated_by',
        ]


class BlogPostCreateSerializer(serializers.ModelSerializer):
    """
    Write serializer for `POST /api/v1/blog/posts/`.

    `status`, `published_at` and `slug` are not accepted: a new post is
    always a draft with a generated slug, and publication is a separate
    operation with its own permission.
    """
    categories = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=CATEGORY_QUERYSET,
        required=False,
    )
    tags = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=TAG_QUERYSET,
        required=False,
    )

    class Meta:
        model = BlogPost
        fields = [
            'id',
            'title',
            'slug',
            'content',
            'author',
            'featured_image',
            'featured_image_alt_text',
            'categories',
            'tags',
            'seo_title',
            'seo_description',
            'seo_focus_keyword',
            'seo_noindex',
            'seo_nofollow',
        ]
        read_only_fields = [
            'id',
            'slug',
        ]

    def create(self, validated_data):
        return create_blog_post(
            validated_data=validated_data,
            user=self.context['request'].user,
        )


class BlogPostUpdateSerializer(serializers.ModelSerializer):
    """
    Write serializer for `PUT`/`PATCH /api/v1/blog/posts/{id}/`.

    Editing a post never moves it between draft and published, and the
    slug stays as generated so existing links keep working.
    """
    categories = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=CATEGORY_QUERYSET,
        required=False,
    )
    tags = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=TAG_QUERYSET,
        required=False,
    )

    class Meta:
        model = BlogPost
        fields = [
            'id',
            'title',
            'slug',
            'content',
            'author',
            'featured_image',
            'featured_image_alt_text',
            'categories',
            'tags',
            'seo_title',
            'seo_description',
            'seo_focus_keyword',
            'seo_noindex',
            'seo_nofollow',
        ]
        read_only_fields = [
            'id',
            'slug',
        ]

    def update(self, instance, validated_data):
        return update_blog_post(
            post=instance,
            validated_data=validated_data,
            user=self.context['request'].user,
        )
