# product_api/services/__init__.py
from .brand import BrandService
from .product import (
    upload_product_image,
    replace_product_image,
    set_product_image_default,
    reorder_product_images,
    increment_product_view_count,
    get_or_create_default_variant,
    soft_delete_product,
)
from .product_image import (
    get_product_image_summary,
    get_product_image_dimensions,
    is_product_image_high_resolution,
    is_product_image_ratio_mismatch,
    optimize_product_image,
    bulk_optimize_product_images,
    set_product_image_resolution,
    recalculate_product_image_resolution,
    start_product_image_recalc_run,
    record_product_image_recalc_batch,
    get_product_image_recalc_run,
    RECALC_BATCH_SIZE,
    soft_delete_product_image,
    bulk_upload_product_images,
)


__all__ = [
    'BrandService',
    'upload_product_image',
    'replace_product_image',
    'set_product_image_default',
    'reorder_product_images',
    'soft_delete_product_image',
    'bulk_upload_product_images',
    'increment_product_view_count',
    'get_or_create_default_variant',
    'soft_delete_product',
    "get_product_image_summary",
    'get_product_image_dimensions',
    'is_product_image_high_resolution',
    'is_product_image_ratio_mismatch',
    'optimize_product_image',
    'bulk_optimize_product_images',
    'set_product_image_resolution',
    'recalculate_product_image_resolution',
    'start_product_image_recalc_run',
    'record_product_image_recalc_batch',
    'get_product_image_recalc_run',
    'RECALC_BATCH_SIZE',
]
