# product_api/services/product_image.py
from django.db import transaction
from django.db.models import Count, F, Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from PIL import Image, ImageOps

import logging

from product_api.models import ProductImage
from product_api.utils import optimize_image_file


logger = logging.getLogger(__name__)


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


def read_image_dimensions(image_source):
    """
    Read (width, height) from an image file or field.

    The EXIF orientation is applied so the returned size matches the
    displayed size. This opens the image file and is meant for write
    time, not for request-time reads.
    """
    with Image.open(image_source) as image_file:
        image = ImageOps.exif_transpose(image_file)
        image.load()
        return image.size


def set_product_image_resolution(product_image):
    """Compute and persist width/height from the stored image file."""
    width, height = read_image_dimensions(product_image.image)
    product_image.width = width
    product_image.height = height
    product_image.save(update_fields=['width', 'height'])
    return product_image


def get_product_image_dimensions(product_image):
    """Return the stored (width, height) of a product image."""
    return product_image.width, product_image.height


def get_product_image_flags(product_image):
    """Return derived flags for a product image."""
    return {
        'is_high_resolution': is_product_image_high_resolution(
            product_image
        ),
        'is_ratio_mismatch': is_product_image_ratio_mismatch(
            product_image
        ),
    }


def is_product_image_high_resolution(product_image):
    """Return True when width or height is greater than 500 pixels."""
    return product_image.width > 500 or product_image.height > 500


def is_product_image_ratio_mismatch(product_image):
    """Return True when the image is not square."""
    return product_image.width != product_image.height


def get_product_image_summary(product_images):
    """
    Return summary statistics aggregated from the stored width/height
    columns, without opening any image file.
    """
    return product_images.aggregate(
        total_products=Count('product', distinct=True),
        total_product_images=Count('id'),
        high_resolution_images=Count(
            'id',
            filter=Q(width__gt=500) | Q(height__gt=500),
        ),
        ratio_mismatch_images=Count(
            'id',
            filter=~Q(width=F('height')),
        ),
    )


def recalculate_product_image_resolution(product_images):
    """
    Recompute width/height for every supplied image, counting any whose
    file cannot be read as failed.
    """
    total = 0
    updated = 0
    failed = 0

    for product_image in product_images.iterator(chunk_size=100):
        total += 1
        try:
            set_product_image_resolution(product_image)
        except Exception:
            logger.exception(
                'Failed to recalculate resolution for product '
                'image ID %s',
                product_image.id,
            )
            failed += 1
        else:
            updated += 1

    return {
        'total': total,
        'updated': updated,
        'failed': failed,
    }


def optimize_product_image(image_instance, updated_by=None):
    """
    Optimize a product image by limiting its largest dimension
    to 500px while preserving its aspect ratio.
    """
    if image_instance is None:
        raise ValidationError(
            'A product image is required.'
        )

    if not image_instance.image:
        raise ValidationError(
            'Product image file is missing.'
        )

    image_field = image_instance.image
    original_name = image_field.name
    original_size = image_field.size

    with image_field.open('rb') as original_file:
        optimized_file, metadata = optimize_image_file(
            original_file,
            max_dimension=500,
        )

    if optimized_file.size >= original_size:
        optimized_file.close()
        return {
            'optimized': False,
            'message': 'Image is already optimized or cannot be reduced further.',  # noqa
            **metadata,
        }

    storage = image_field.storage

    try:
        with transaction.atomic():
            image_instance.image.save(
                original_name,
                optimized_file,
                save=False,
            )

            image_instance.width = (
                metadata['optimized_dimensions']['width']
            )
            image_instance.height = (
                metadata['optimized_dimensions']['height']
            )
            image_instance.updated_by = updated_by

            image_instance.save(
                update_fields=[
                    'image',
                    'width',
                    'height',
                    'updated_by',
                    'updated_at',
                ]
            )

            new_name = image_instance.image.name

            transaction.on_commit(
                lambda: storage.delete(original_name)
                if original_name != new_name
                else None
            )

    except Exception:
        optimized_file.close()
        raise

    optimized_file.close()

    return {
        'optimized': True,
        **metadata,
    }


def bulk_optimize_product_images(image_ids, updated_by=None):
    """
    Optimize multiple product images independently.

    Images that already satisfy the dimension limit are skipped.
    Individual failures do not interrupt the remaining images.
    """
    images = ProductImage.objects.filter(
        id__in=image_ids,
        is_active=True,
        deleted_at__isnull=True,
    ).in_bulk()

    results = []

    for image_id in image_ids:
        image_instance = images.get(image_id)

        if image_instance is None:
            results.append({
                'id': image_id,
                'status': 'not_found',
                'message': 'Product image not found.',
            })
            continue

        try:
            if not image_instance.image:
                raise ValidationError('Image file is missing.')

            with image_instance.image.open('rb') as image_file:
                with Image.open(image_file) as source:
                    image = ImageOps.exif_transpose(source)
                    width, height = image.size

            if max(width, height) <= 500:
                results.append({
                    'id': image_id,
                    'status': 'skipped',
                    'message': 'Image dimensions are already within the limit.',    # noqa
                    'original_dimensions': {
                        'width': width,
                        'height': height,
                    },
                    'optimized_dimensions': {
                        'width': width,
                        'height': height,
                    },
                })
                continue

            result = optimize_product_image(
                image_instance=image_instance,
                updated_by=updated_by,
            )

            results.append({
                'id': image_id,
                'status': 'optimized',
                **result,
            })

        except ValidationError as exc:
            results.append({
                'id': image_id,
                'status': 'failed',
                'message': ' '.join(exc.messages),
            })

        except Exception:
            logger.exception(
                'Failed to optimize product image ID %s',
                image_id,
            )

            results.append({
                'id': image_id,
                'status': 'failed',
                'message': 'An unexpected error occurred during optimization.',
            })

    return {
        'total': len(image_ids),
        'optimized': sum(
            item['status'] == 'optimized' for item in results
        ),
        'skipped': sum(
            item['status'] == 'skipped' for item in results
        ),
        'failed': sum(
            item['status'] == 'failed' for item in results
        ),
        'not_found': sum(
            item['status'] == 'not_found' for item in results
        ),
        'results': results,
    }


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


def bulk_upload_product_images(
    product,
    images_data,
    created_by=None,
    updated_by=None,
):
    """Create multiple product images atomically."""
    if product is None:
        raise ValidationError(
            'A product is required to upload images.'
        )

    if not images_data:
        raise ValidationError(
            'At least one image is required.'
        )

    with transaction.atomic():
        existing_images = list(
            ProductImage.objects.select_for_update().filter(
                product=product,
                is_active=True,
            ).order_by(
                'display_order',
                'created_at',
                'id',
            )
        )

        has_existing_default = any(
            image.is_default
            for image in existing_images
        )

        next_display_order = (
            max(
                (
                    image.display_order
                    for image in existing_images
                ),
                default=-1,
            )
            + 1
        )

        created_images = []

        explicitly_default = next(
            (
                item
                for item in images_data
                if item.get('is_default', False)
            ),
            None,
        )

        for index, item in enumerate(images_data):
            display_order = item.get('display_order')

            if display_order is None:
                display_order = next_display_order + index

            alt_text = item.get('alt_text') or product.name

            image = ProductImage.objects.create(
                product=product,
                image=item['image'],
                alt_text=alt_text,
                display_order=display_order,
                is_default=False,
                created_by=created_by,
                updated_by=updated_by,
            )
            set_product_image_resolution(image)

            created_images.append(image)

        #
        # Explicit default image.
        #
        if explicitly_default is not None:
            default_index = images_data.index(explicitly_default)

            default_image = created_images[default_index]

            ProductImage.objects.filter(
                product=product,
                is_active=True,
                is_default=True,
            ).exclude(
                pk=default_image.pk,
            ).update(
                is_default=False,
                updated_by=updated_by,
            )

            default_image.is_default = True
            default_image.updated_by = updated_by
            default_image.save(
                update_fields=[
                    'is_default',
                    'updated_by',
                    'updated_at',
                ]
            )

        #
        # No explicit default.
        #
        elif not has_existing_default:
            first_image = created_images[0]

            first_image.is_default = True
            first_image.updated_by = updated_by
            first_image.save(
                update_fields=[
                    'is_default',
                    'updated_by',
                    'updated_at',
                ]
            )

        return created_images
