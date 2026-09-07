# blog_api/filters.py
import django_filters

from blog_api.models import BlogPost


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
