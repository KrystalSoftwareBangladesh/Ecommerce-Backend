# product_api/services/product_image.py
from PIL import Image


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
