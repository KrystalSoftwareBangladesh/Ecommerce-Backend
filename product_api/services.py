# product_api/services.py
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import ProductImage


def _get_active_images(product):
    return list(
        ProductImage.objects.filter(product=product, is_active=True).order_by(
            'display_order', 'created_at', 'id'
        )
    )


def _reindex_display_order(product):
    images = _get_active_images(product)
    for index, image in enumerate(images, start=1):
        image.display_order = index
        image.save(update_fields=['display_order', 'updated_at'])


def _get_next_display_order(product):
    last_image = (
        ProductImage.objects.filter(product=product, is_active=True)
        .order_by('-display_order', '-created_at', '-id')
        .first()
    )
    if last_image is None:
        return 1
    return last_image.display_order + 1


def upload_product_image(
    product,
    image_file,
    alt_text='',
    created_by=None,
    updated_by=None,
):
    """Create a new product image and assign its initial ordering/defaults."""
    if product is None:
        raise ValidationError('A product is required to upload an image.')
    if image_file is None:
        raise ValidationError('An image file is required.')

    with transaction.atomic():
        is_first_image = not ProductImage.objects.filter(
            product=product,
            is_active=True,
        ).exists()

        image = ProductImage.objects.create(
            product=product,
            image=image_file,
            alt_text=alt_text,
            display_order=_get_next_display_order(product),
            is_default=is_first_image,
            created_by=created_by,
            updated_by=updated_by,
        )

        return image


def replace_product_image(image_instance, new_image_file, updated_by=None):
    """Replace the uploaded file while preserving image metadata and flags."""
    if image_instance is None:
        raise ValidationError('A product image is required.')
    if new_image_file is None:
        raise ValidationError('A replacement image file is required.')

    with transaction.atomic():
        image_instance.image = new_image_file
        image_instance.updated_by = updated_by
        image_instance.save()
        return image_instance


def set_product_image_default(image_instance, updated_by=None):
    """Set requested image as default and clear previous default."""
    if image_instance is None:
        raise ValidationError('A product image is required.')
    if not image_instance.is_active:
        raise ValidationError('Only active images can be marked as default.')

    with transaction.atomic():
        active_images = list(
            ProductImage.objects.select_for_update().filter(
                product=image_instance.product,
                is_active=True,
            ).order_by('display_order', 'created_at', 'id')
        )

        if not active_images:
            raise ValidationError('No active images are available.')

        for image in active_images:
            if image.pk != image_instance.pk and image.is_default:
                image.is_default = False
                image.updated_by = updated_by
                image.save(
                    update_fields=['is_default', 'updated_by', 'updated_at']
                )

        image_instance.is_default = True
        image_instance.updated_by = updated_by
        image_instance.save(
            update_fields=['is_default', 'updated_by', 'updated_at']
        )

        return image_instance


def reorder_product_images(
    product,
    image_id,
    new_display_order,
    updated_by=None,
):
    """Reorder product images and maintain sequential display_order values."""
    if product is None:
        raise ValidationError('A product is required to reorder images.')
    if new_display_order is None:
        raise ValidationError('A new display order is required.')
    if new_display_order < 1:
        raise ValidationError('Display order must start at 1.')

    with transaction.atomic():
        images = list(
            ProductImage.objects.select_for_update().filter(
                product=product,
                is_active=True,
            ).order_by('display_order', 'created_at', 'id')
        )

        target_image = next(
            (image for image in images if image.pk == image_id),
            None,
        )
        if target_image is None:
            raise ValidationError('The requested image was not found.')

        images.remove(target_image)
        new_position = min(max(new_display_order, 1), len(images) + 1)
        images.insert(new_position - 1, target_image)

        for index, image in enumerate(images, start=1):
            image.display_order = index
            image.updated_by = updated_by
            image.save(
                update_fields=['display_order', 'updated_by', 'updated_at']
            )

        return images


def soft_delete_product_image(image_instance, deleted_by=None):
    """Soft delete an image and assign a new default if needed."""
    if image_instance is None:
        raise ValidationError('A product image is required.')

    with transaction.atomic():
        image_instance.updated_by = deleted_by
        image_instance.is_active = False
        image_instance.deleted_at = timezone.now()
        image_instance.save(
            update_fields=[
                'is_active',
                'deleted_at',
                'updated_by',
                'updated_at',
            ]
        )

        if image_instance.is_default:
            remaining_images = list(
                ProductImage.objects.select_for_update().filter(
                    product=image_instance.product,
                    is_active=True,
                ).order_by('display_order', 'created_at', 'id')
            )
            if remaining_images:
                next_default = remaining_images[0]
                next_default.is_default = True
                next_default.updated_by = deleted_by
                next_default.save(
                    update_fields=[
                        'is_default',
                        'updated_by',
                        'updated_at',
                    ]
                )

        _reindex_display_order(image_instance.product)

        return image_instance
