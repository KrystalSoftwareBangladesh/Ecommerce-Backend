# product_api/tasks.py
from celery import shared_task

from django.contrib.auth import get_user_model

from product_api.models import ProductImage
from product_api.services import (
    bulk_optimize_product_images,
    recalculate_product_image_resolution,
    record_product_image_optimize_result,
    record_product_image_recalc_batch,
)


@shared_task
def recalculate_product_image_resolution_task(image_ids, run_id):
    """
    Recalculate resolution for one batch of product images and add
    the batch counts to the run counters.
    """
    result = recalculate_product_image_resolution(
        ProductImage.objects.filter(id__in=image_ids)
    )
    record_product_image_recalc_batch(
        run_id,
        processed=result['total'],
        updated=result['updated'],
        failed=result['failed'],
    )
    return result


@shared_task
def optimize_product_image_task(image_id, run_id, updated_by_id=None):
    """
    Optimize one product image and record its per-image result
    in the async bulk-optimize run counters.
    """
    updated_by = None

    if updated_by_id is not None:
        updated_by = get_user_model().objects.filter(
            pk=updated_by_id,
        ).first()

    outcome = bulk_optimize_product_images(
        [image_id], updated_by=updated_by,
    )
    result = outcome['results'][0]
    record_product_image_optimize_result(run_id, result)
    return result
