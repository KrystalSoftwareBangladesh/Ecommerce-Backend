# product_api/services/product.py
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from product_api.models import ProductImage, Product, ProductVariant

from .product_image import set_product_image_resolution


DEFAULT_VARIANT_SKU_PREFIX = 'P-'


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
        set_product_image_resolution(image)

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
        set_product_image_resolution(image_instance)
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
    """Reorder product images using zero-based display order."""
    if product is None:
        raise ValidationError('A product is required to reorder images.')

    if new_display_order is None:
        raise ValidationError('A new display order is required.')

    if new_display_order < 0:
        raise ValidationError(
            'Display order must be greater than or equal to 0.'
        )

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

        new_position = min(
            max(new_display_order, 0),
            len(images),
        )

        images.insert(new_position, target_image)

        for index, image in enumerate(images):
            image.display_order = index
            image.updated_by = updated_by
            image.save(
                update_fields=[
                    'display_order',
                    'updated_by',
                    'updated_at',
                ]
            )

        return images


def increment_product_view_count(*, product: Product) -> None:
    Product.objects.filter(
        pk=product.pk,
        is_active=True,
        deleted_at__isnull=True,
    ).update(
        view_count=F("view_count") + 1,
    )


def _default_variant_sku(product):
    """
    Return an unused SKU for the product's default variant.

    The base form is ``P-<product id>``. Should a staff-entered variant
    already use that SKU (compared case-insensitively, as the product
    serializer does), a numeric suffix is appended.
    """
    base = f"{DEFAULT_VARIANT_SKU_PREFIX}{product.pk}"
    sku = base
    suffix = 2
    while ProductVariant.objects.filter(
        sku__iexact=sku, is_active=True,
    ).exists():
        sku = f"{base}-{suffix}"
        suffix += 1
    return sku


def get_or_create_default_variant(*, product):
    """
    Return the product's active variant, creating a default one when
    the product has none.

    Sales, reservations and the inventory ledger are keyed by
    ``ProductVariant``, but imported catalogue products carry no
    variants. The default variant (SKU ``P-<product id>``, no colour or
    size) lets such a product be sold without changing those ledgers.

    The product row is locked so two concurrent checkouts cannot create
    two default variants; callers must run inside a transaction. If an
    active variant appears while waiting for the lock, that variant is
    returned instead.
    """
    if product is None:
        raise ValidationError('A product is required.')

    with transaction.atomic():
        locked_product = (
            Product.objects.select_for_update().get(pk=product.pk)
        )
        existing = (
            locked_product.variants.filter(
                is_active=True, deleted_at__isnull=True,
            )
            .order_by('sku', 'pk')
            .first()
        )
        if existing is not None:
            return existing
        return ProductVariant.objects.create(
            product=locked_product,
            sku=_default_variant_sku(locked_product),
        )


def soft_delete_product(product, deleted_by=None):
    """Soft delete a product and all its active images."""

    if product is None:
        raise ValidationError('A product is required.')

    with transaction.atomic():
        now = timezone.now()

        # Soft delete the product.
        product.is_active = False
        product.save(update_fields=['is_active', 'updated_at'])

        # Soft delete all active images belonging to the product.
        ProductImage.objects.filter(
            product=product,
            is_active=True,
            deleted_at__isnull=True,
        ).update(
            is_active=False,
            deleted_at=now,
            updated_by=deleted_by,
            updated_at=now,
        )

        return product
