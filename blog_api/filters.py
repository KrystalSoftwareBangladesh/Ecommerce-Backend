# blog_api/filters.py
import django_filters
from django.db.models import Exists, OuterRef

from blog_api.models import BlogPost, BlogTag


class BlogPostFilter(django_filters.FilterSet):
    """
    Filters for the blog post list.

    Every filter is applied on top of the queryset the ViewSet already
    narrowed, so an anonymous caller asking for `?status=DRAFT` filters
    within published posts and gets nothing back rather than a draft.
    """
    category = django_filters.NumberFilter(
        field_name='categories__id',
        help_text='Identifier of a category the post belongs to',
    )
    categories = django_filters.BaseInFilter(
        field_name='categories__id',
        lookup_expr='in',
        help_text='Comma-separated category IDs',
    )
    category_slug = django_filters.CharFilter(
        field_name='categories__slug',
        help_text='Slug of a category the post belongs to',
    )
    tag = django_filters.NumberFilter(
        field_name='tags__id',
        help_text='Identifier of a tag attached to the post',
    )
    tag_slug = django_filters.CharFilter(
        field_name='tags__slug',
        help_text='Slug of a tag attached to the post',
    )
    author = django_filters.NumberFilter(
        field_name='author_id',
        help_text='Identifier of the post author',
    )
    published_after = django_filters.IsoDateTimeFilter(
        field_name='published_at',
        lookup_expr='gte',
        help_text='Only posts published at or after this timestamp',
    )
    published_before = django_filters.IsoDateTimeFilter(
        field_name='published_at',
        lookup_expr='lte',
        help_text='Only posts published at or before this timestamp',
    )

    class Meta:
        model = BlogPost
        fields = [
            'status',
        ]


class BlogTagFilter(django_filters.FilterSet):
    """
    Filters for the blog tag list.

    Mirrors `category_api.filters.CategoryFilter`: the `no_blog_post`
    filter is an `Exists` subquery, so it adds no join and cannot
    duplicate or drop rows in the list.
    """
    no_blog_post = django_filters.BooleanFilter(
        method='filter_no_blog_post',
        help_text=(
            'If true, only tags with no active blog post; '
            'if false, only tags with at least one.'
        ),
    )

    class Meta:
        model = BlogTag
        fields = ['is_active']

    def filter_no_blog_post(self, queryset, name, value):
        condition = BlogPost.objects.filter(
            tags=OuterRef('pk'),
            is_active=True,
            deleted_at__isnull=True,
        )
        if value is True:
            return queryset.filter(~Exists(condition))
        elif value is False:
            return queryset.filter(Exists(condition))
        return queryset
