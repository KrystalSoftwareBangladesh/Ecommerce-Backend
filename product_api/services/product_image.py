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
