# category_api/services/featured_category.py
from django.db import transaction
from django.core.files.storage import default_storage
from rest_framework.exceptions import ValidationError

from category_api.models import Category


def _delete_storage_file(file_name: str | None) -> None:
    if not file_name:
        return

    if default_storage.exists(file_name):
        default_storage.delete(file_name)


@transaction.atomic
def mark_category_as_featured(*, category, user):
    if category.is_featured:
        raise ValidationError(
            {
                "detail": "This category is already featured."
            }
        )

    if not category.featured_icon:
        raise ValidationError(
            {
                "featured_icon": (
                    "A featured icon is required before marking "
                    "the category as featured."
                )
            }
        )

    category.is_featured = True

    # Put the category at the end of the current featured list.
    last_featured_order = (
        Category.objects
        .filter(
            is_featured=True,
            is_active=True,
            deleted_at__isnull=True,
        )
        .exclude(pk=category.pk)
        .order_by("-featured_display_order")
        .values_list("featured_display_order", flat=True)
        .first()
    )

    category.featured_display_order = (
        (last_featured_order + 1)
        if last_featured_order is not None
        else 0
    )

    category.save(
        update_fields=[
            "is_featured",
            "featured_display_order",
            "updated_at",
        ]
    )

    return category


@transaction.atomic
def remove_category_from_featured(*, category, user):
    if not category.is_featured:
        raise ValidationError(
            {
                "detail": "This category is not featured."
            }
        )

    category.is_featured = False
    category.featured_display_order = 0

    category.save(
        update_fields=[
            "is_featured",
            "featured_display_order",
            "updated_at",
        ]
    )

    return category


@transaction.atomic
def upload_featured_category_icon(*, category, featured_icon, user):
    if not featured_icon:
        raise ValidationError({
            "featured_icon": "Featured icon is required."
        })

    old_icon_name = category.featured_icon.name

    category.featured_icon = featured_icon
    category.save(
        update_fields=[
            "featured_icon",
            "updated_at",
        ]
    )

    new_icon_name = category.featured_icon.name

    if (
        old_icon_name
        and old_icon_name != new_icon_name
    ):
        transaction.on_commit(
            lambda: _delete_storage_file(old_icon_name)
        )

    return category


@transaction.atomic
def reorder_featured_categories(*, category_ids, user):
    featured_categories = list(
        Category.objects
        .select_for_update()
        .filter(
            is_featured=True,
            is_active=True,
            deleted_at__isnull=True,
        )
        .order_by("featured_display_order", "id")
    )

    featured_category_ids = {
        category.id
        for category in featured_categories
    }

    submitted_category_ids = set(category_ids)

    if submitted_category_ids != featured_category_ids:
        missing_ids = sorted(
            featured_category_ids - submitted_category_ids
        )

        invalid_ids = sorted(
            submitted_category_ids - featured_category_ids
        )

        error_detail = {}

        if missing_ids:
            error_detail["missing_category_ids"] = (
                "All currently featured categories must be included."
            )

        if invalid_ids:
            error_detail["invalid_category_ids"] = (
                "Every category ID must belong to an active featured category."
            )

        raise ValidationError(error_detail)

    categories_by_id = {
        category.id: category
        for category in featured_categories
    }

    updated_categories = []

    for display_order, category_id in enumerate(category_ids):
        category = categories_by_id[category_id]

        if category.featured_display_order != display_order:
            category.featured_display_order = display_order

            category.save(
                update_fields=[
                    "featured_display_order",
                    "updated_at",
                ]
            )

        updated_categories.append(category)

    return updated_categories


@transaction.atomic
def remove_featured_category_icon(*, category, user):
    if category.is_featured:
        raise ValidationError({
            "featured_icon": (
                "You must remove this category from featured "
                "categories before deleting its icon."
            )
        })

    if not category.featured_icon:
        raise ValidationError({
            "featured_icon": "This category does not have an icon."
        })

    icon_name = category.featured_icon.name

    category.featured_icon = None
    category.save(
        update_fields=[
            "featured_icon",
            "updated_at",
        ]
    )

    transaction.on_commit(
        lambda: _delete_storage_file(icon_name)
    )

    return category
