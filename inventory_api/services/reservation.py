# inventory_api/services/reservation.py
"""
Inventory reservation services for storefront
order creation.

Conventions:
- All operations use transaction.atomic().
- Variants are locked with select_for_update()
  in a deterministic order (by PK) to reduce
  deadlock risk.
- Soft-deleted movements are excluded from stock
  calculations.
- Expired reservations are excluded from available
  stock.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from inventory_api.models import (
    InventoryMovement,
    InventoryReservation,
    MovementType,
    ReferenceType,
    ReservationStatus,
)


def get_available_stock(
    product_variant, exclude_sale=None
):
    """
    Calculate available stock for a variant.

    Available = active movements - active,
    unexpired reservations.

    If exclude_sale is provided, reservations for
    that sale are excluded from the reserved total.
    This is used during confirmation to check stock
    excluding the current order's own reservations.
    """
    total_movements = (
        InventoryMovement.objects.filter(
            product_variant=product_variant,
            is_active=True,
        ).aggregate(
            stock=Sum('quantity')
        )['stock']
        or 0
    )

    reservation_qs = (
        InventoryReservation.objects.filter(
            product_variant=product_variant,
            status=ReservationStatus.ACTIVE,
            expires_at__gt=timezone.now(),
        )
    )
    if exclude_sale is not None:
        reservation_qs = reservation_qs.exclude(
            sale=exclude_sale,
        )

    total_reserved = (
        reservation_qs.aggregate(
            reserved=Sum('quantity')
        )['reserved']
        or 0
    )

    return total_movements - total_reserved


@transaction.atomic
def reserve_stock(sale, items, user=None):
    """
    Reserve stock for an order.

    ``items`` is an iterable of dicts, each with:
    - ``product_variant``: a ProductVariant instance
    - ``quantity``: int > 0

    Variants are locked in PK order to reduce
    deadlock risk.

    Raises ValidationError if stock is insufficient.
    Returns the list of created reservations.
    """
    minutes = getattr(
        settings,
        'CHECKOUT_RESERVATION_MINUTES',
        30,
    )
    expires_at = timezone.now() + timezone.timedelta(
        minutes=minutes,
    )

    # Sort by variant PK for deterministic locking.
    sorted_items = sorted(
        items,
        key=lambda x: x['product_variant'].pk,
    )

    reservations = []
    for item in sorted_items:
        variant = item['product_variant']
        quantity = item['quantity']

        if quantity < 1:
            raise ValidationError(
                f"Reservation quantity must be >= 1 "
                f"for {variant}."
            )

        # Lock the variant row.
        locked_variant = (
            type(variant).objects
            .select_for_update()
            .get(pk=variant.pk)
        )

        available = get_available_stock(
            locked_variant
        )
        if available < quantity:
            raise ValidationError(
                f"Insufficient stock for "
                f"{variant}: requested {quantity}, "
                f"available {available}."
            )

        reservation = (
            InventoryReservation.objects.create(
                product_variant=locked_variant,
                sale=sale,
                quantity=quantity,
                status=ReservationStatus.ACTIVE,
                expires_at=expires_at,
                created_by=user,
                updated_by=user,
            )
        )
        reservations.append(reservation)

    return reservations


@transaction.atomic
def consume_reservations(sale, user=None):
    """
    Convert ACTIVE reservations to CONSUMED and
    create inventory movements (stock deduction).

    Called during sale confirmation. Each reservation
    is locked with select_for_update() before
    processing to prevent TOCTOU races with
    concurrent release or expiry.

    Raises ValidationError if any reservation is
    missing, not ACTIVE, or expired.

    Returns the list of consumed reservations.
    """
    # Lock reservations first to prevent concurrent
    # release/expiry from changing status between
    # our check and our update.
    now = timezone.now()
    locked_reservations = list(
        InventoryReservation.objects.filter(
            sale=sale,
            status=ReservationStatus.ACTIVE,
            expires_at__gt=now,
        )
        .select_related('product_variant')
        .select_for_update()
    )

    if not locked_reservations:
        # Check if there are any reservations at all
        # (for a better error message).
        any_exist = (
            InventoryReservation.objects.filter(
                sale=sale,
            ).exists()
        )
        if any_exist:
            raise ValidationError(
                "No active reservations found. "
                "They may have been consumed, "
                "released, or expired."
            )
        raise ValidationError(
            "No reservations found for this sale."
        )

    # Lock variants in PK order.
    variant_pks = sorted(
        set(
            r.product_variant_id
            for r in locked_reservations
        )
    )
    locked_variants = {}
    for pk in variant_pks:
        from product_api.models import ProductVariant
        locked_variants[pk] = (
            ProductVariant.objects
            .select_for_update()
            .get(pk=pk)
        )

    consumed = []
    for reservation in locked_reservations:
        # Re-verify stock excluding our own sale.
        variant = locked_variants[
            reservation.product_variant_id
        ]
        available = get_available_stock(
            variant, exclude_sale=sale
        )
        if available < reservation.quantity:
            raise ValidationError(
                f"Stock no longer available for "
                f"{variant}: requested "
                f"{reservation.quantity}, "
                f"available {available}."
            )

        # Create movement (stock deduction).
        InventoryMovement.objects.create(
            product_variant=variant,
            quantity=-reservation.quantity,
            movement_type=MovementType.SALE,
            reference_type=ReferenceType.ORDER,
            reference_id=sale.pk,
            created_by=user,
            updated_by=user,
        )

        reservation.status = (
            ReservationStatus.CONSUMED
        )
        reservation.updated_by = user
        reservation.save(
            update_fields=[
                'status',
                'updated_by',
                'updated_at',
            ]
        )
        consumed.append(reservation)

    return consumed


@transaction.atomic
def release_reservations(sale, user=None):
    """
    Release ACTIVE reservations for a sale.

    Called during cancellation. Idempotent — running
    twice changes zero rows the second time.

    Returns the number of reservations released.
    """
    count = (
        InventoryReservation.objects.filter(
            sale=sale,
            status=ReservationStatus.ACTIVE,
        ).update(
            status=ReservationStatus.RELEASED,
            updated_by=user,
            updated_at=timezone.now(),
        )
    )
    return count


def expire_reservations(batch_size=1000):
    """
    Release stale ACTIVE reservations.

    Safe to rerun. Processes in bounded batches.
    Returns the total number of reservations
    released.
    """
    now = timezone.now()
    total = 0

    while True:
        # Find expired ACTIVE reservation IDs
        # in bounded batches.
        ids = list(
            InventoryReservation.objects.filter(
                status=ReservationStatus.ACTIVE,
                expires_at__lte=now,
            )
            .order_by('id')
            .values_list('id', flat=True)[
                :batch_size
            ]
        )

        if not ids:
            break

        updated = (
            InventoryReservation.objects.filter(
                id__in=ids,
                status=ReservationStatus.ACTIVE,
            ).update(
                status=ReservationStatus.RELEASED,
                updated_at=now,
            )
        )
        total += updated

    return total
