# product_api/tasks.py
from celery import shared_task

from product_api.models import ProductImage
from product_api.services import (
    recalculate_product_image_resolution,
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
