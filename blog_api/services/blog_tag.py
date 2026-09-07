# blog_api/services/blog_tag.py
from django.db import transaction

from blog_api.models import BlogTag


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

    Posts keep their relationship to the tag; the tag simply stops being
    listed and stops being selectable.
    """
    tag.updated_by = user
    tag.save(update_fields=['updated_by', 'updated_at'])

    tag.soft_delete()

    return tag
