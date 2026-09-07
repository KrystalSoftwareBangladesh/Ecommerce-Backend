# blog_api/services/blog_post.py
from django.db import transaction
from django.utils import timezone

from rest_framework.exceptions import ValidationError

from blog_api.models import BlogPost, BlogPostStatus


@transaction.atomic
def create_blog_post(*, validated_data, user):
    """
    Create a blog post.

    Business Rules
    --------------
    - A new post is always a draft; `status` and `published_at` are not
      client input.
    - The author defaults to the user creating the post.
    - The slug is generated from the title on first save and never
      changes afterwards.
    """
    categories = validated_data.pop('categories', [])
    tags = validated_data.pop('tags', [])
    author = validated_data.pop('author', None) or user

    # Publication is a separate operation with its own permission, so
    # these never come from the caller however the data was assembled.
    validated_data.pop('status', None)
    validated_data.pop('published_at', None)

    post = BlogPost.objects.create(
        **validated_data,
        author=author,
        status=BlogPostStatus.DRAFT,
        published_at=None,
        created_by=user,
        updated_by=user,
    )

    post.categories.set(categories)
    post.tags.set(tags)

    return post


@transaction.atomic
def update_blog_post(*, post, validated_data, user):
    """
    Update a blog post.

    Business Rules
    --------------
    - Editing never changes the publication state: a published post stays
      published, a draft stays a draft.
    - The slug is immutable, so it is not accepted here.
    """
    has_categories = 'categories' in validated_data
    has_tags = 'tags' in validated_data

    categories = validated_data.pop('categories', None)
    tags = validated_data.pop('tags', None)

    validated_data.pop('status', None)
    validated_data.pop('published_at', None)

    for field, value in validated_data.items():
        setattr(post, field, value)

    post.updated_by = user
    post.save()

    if has_categories:
        post.categories.set(categories)

    if has_tags:
        post.tags.set(tags)

    return post


def delete_blog_post(*, post, user):
    """
    Soft delete a blog post, keeping the audit trail.
    """
    post.updated_by = user
    post.save(update_fields=['updated_by', 'updated_at'])

    post.soft_delete()

    return post


@transaction.atomic
def publish_blog_post(*, post, user):
    """
    Publish a draft post.

    Business Rules
    --------------
    - Only a draft can be published.
    - Publishing stamps `published_at` with the moment of publication.
    """
    if post.status == BlogPostStatus.PUBLISHED:
        raise ValidationError('This post is already published.')

    post.status = BlogPostStatus.PUBLISHED
    post.published_at = timezone.now()
    post.updated_by = user
    post.save(
        update_fields=[
            'status',
            'published_at',
            'updated_by',
            'updated_at',
        ]
    )

    return post


@transaction.atomic
def unpublish_blog_post(*, post, user):
    """
    Return a published post to draft.

    Business Rules
    --------------
    - Only a published post can be unpublished.
    - Unpublishing clears `published_at`; republishing stamps a new one.
    """
    if post.status != BlogPostStatus.PUBLISHED:
        raise ValidationError('This post is not published.')

    post.status = BlogPostStatus.DRAFT
    post.published_at = None
    post.updated_by = user
    post.save(
        update_fields=[
            'status',
            'published_at',
            'updated_by',
            'updated_at',
        ]
    )

    return post
