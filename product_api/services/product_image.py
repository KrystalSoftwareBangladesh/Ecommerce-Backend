# product_api/services/product_image.py
from django.db import transaction
from rest_framework.exceptions import ValidationError

from PIL import Image, ImageOps

import logging

from product_api.models import ProductImage
from product_api.utils import optimize_image_file


logger = logging.getLogger(__name__)


def get_product_image_summary(product_images):
    """Return summary statistics for the supplied product images."""
    total_product_images = 0
    high_resolution_images = 0
    ratio_mismatch_images = 0
    product_ids = set()

    for product_image in product_images.iterator():
        total_product_images += 1
        product_ids.add(product_image.product_id)

        with Image.open(product_image.image) as image_file:
            width, height = image_file.size

        if width > 500 or height > 500:
            high_resolution_images += 1

        if width != height:
            ratio_mismatch_images += 1

    return {
        'total_products': len(product_ids),
        'total_product_images': total_product_images,
        'high_resolution_images': high_resolution_images,
        'ratio_mismatch_images': ratio_mismatch_images,
    }


def get_product_image_dimensions(product_image):
    """Return the width and height of a product image."""
    with Image.open(product_image.image) as image_file:
        return image_file.size


def get_product_image_flags(product_image):
    """Return derived flags for a product image."""
    width, height = get_product_image_dimensions(product_image)

    return {
        'is_high_resolution': width > 500 or height > 500,
        'is_ratio_mismatch': width != height,
    }


def is_product_image_high_resolution(product_image):
    """Return True when width or height is greater than 500 pixels."""
    return get_product_image_flags(
        product_image
    )['is_high_resolution']


def is_product_image_ratio_mismatch(product_image):
    """Return True when the image is not square."""
    return get_product_image_flags(
        product_image
    )['is_ratio_mismatch']


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

            image_instance.updated_by = updated_by

            image_instance.save(
                update_fields=[
                    'image',
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
