# blog_api/services/blog_tag.py
from django.db import transaction
from django.db.models import Count, Q

from rest_framework.exceptions import ValidationError

from blog_api.models import BlogPostStatus, BlogTag


@transaction.atomic
def create_blog_tag(*, validated_data, user):
    """
    Create a blog tag.

    Business Rules
    --------------
    - The slug is generated from the name on first save.
    - `legacy_id` belongs to migration tooling and is not client input.
    """
    return BlogTag.objects.create(
        **validated_data,
        created_by=user,
        updated_by=user,
    )


@transaction.atomic
def update_blog_tag(*, tag, validated_data, user):
    """
    Update a blog tag. The slug is immutable, so it is not accepted here.
    """
    for field, value in validated_data.items():
        setattr(tag, field, value)

    tag.updated_by = user
    tag.save()

    return tag


def delete_blog_tag(*, tag, user):
    """
    Soft delete a blog tag, keeping the audit trail.

    Business Rules
    --------------
    - A tag assigned to any blog post cannot be deleted; the post must
      be detached from the tag first.
    """
    if tag.posts.exists():
        raise ValidationError(
            'This tag is assigned to one or more blog posts and '
            'cannot be deleted.'
        )

    tag.updated_by = user
    tag.save(update_fields=['updated_by', 'updated_at'])

    tag.soft_delete()

    return tag


def get_blog_tags_with_post_counts():
    """
    Tags carrying at least one published blog post.

    Business Rules
    --------------
    - Only published, active, non-deleted posts are counted, for every
      caller.
    - Tags without any such post are not returned.
    - Busiest tag first, then by name.
    """
    return BlogTag.objects.filter(
        is_active=True,
        deleted_at__isnull=True,
    ).annotate(
        blog_post_count=Count(
            'posts',
            filter=Q(
                posts__status=BlogPostStatus.PUBLISHED,
                posts__is_active=True,
                posts__deleted_at__isnull=True,
            ),
        ),
    ).filter(
        blog_post_count__gt=0,
    ).order_by('-blog_post_count', 'name')
