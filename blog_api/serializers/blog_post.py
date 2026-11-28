# blog_api/serializers/blog_post.py
from rest_framework import serializers

from EcommerceBackend.core.serializers.fields import AbsoluteImageField

from category_api.models import Category
from category_api.serializers import CategorySummarySerializer

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
    categories = CategorySummarySerializer(many=True, read_only=True)
    tags = BlogTagSummarySerializer(many=True, read_only=True)
    featured_image = AbsoluteImageField(read_only=True)

    class Meta:
        model = BlogPost
        fields = [
            'id',
            'title',
            'slug',
            'status',
            'published_at',
            'featured_image',
            'featured_image_alt_text',
            'categories',
            'tags',
            'created_at',
        ]


class BlogPostDetailSerializer(serializers.ModelSerializer):
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
            'view_count',
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


class BlogPostCategoryAddSerializer(serializers.Serializer):
    category_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        help_text="List of category IDs to add to the blog post.",
    )


class BlogCategoryCountSerializer(serializers.Serializer):
    """A blog category with the number of blog posts on it."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    slug = serializers.SlugField(read_only=True)
    blog_post_count = serializers.IntegerField(read_only=True)


class BlogPostMostViewedSerializer(serializers.Serializer):
    """A blog post in the most-viewed listing.

    `name` is the post title.
    """

    id = serializers.IntegerField(read_only=True)
    slug = serializers.SlugField(read_only=True)
    name = serializers.CharField(source='title', read_only=True)
    view_count = serializers.IntegerField(read_only=True)
