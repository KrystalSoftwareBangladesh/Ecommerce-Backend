# banner_api/services/banner.py
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from banner_api.models import Banner


class BannerReorderError(Exception):
    """Raised when banner reordering cannot be completed."""


def get_available_banners(*, placement=None):
    """
    Return banners that are active and currently within their
    configured schedule.
    """
    now = timezone.now()

    queryset = Banner.objects.filter(
        is_active=True,
    ).filter(
        Q(start_at__isnull=True) | Q(start_at__lte=now),
        Q(end_at__isnull=True) | Q(end_at__gte=now),
    ).select_related("placement")

    if placement:
        queryset = queryset.filter(placement=placement)

    return queryset.order_by("display_order", "-created_at")


@transaction.atomic
def reorder_banners(*, placement, banner_orders):
    """
    Reorder banners belonging to a specific placement.

    banner_orders example:
        [
            {"id": 10, "display_order": 0},
            {"id": 15, "display_order": 1},
            {"id": 20, "display_order": 2},
        ]
    """
    banner_ids = [item["id"] for item in banner_orders]

    banners = list(
        Banner.objects.filter(
            id__in=banner_ids,
            placement=placement,
        )
    )

    found_ids = {banner.id for banner in banners}
    missing_ids = set(banner_ids) - found_ids

    if missing_ids:
        raise BannerReorderError(
            f"Banner(s) not found for this placement: "
            f"{sorted(missing_ids)}"
        )

    order_map = {
        item["id"]: item["display_order"]
        for item in banner_orders
    }

    now = timezone.now()

    for banner in banners:
        banner.display_order = order_map[banner.id]
        banner.updated_at = now

    Banner.objects.bulk_update(
        banners,
        ["display_order", "updated_at"],
    )

    return banners
