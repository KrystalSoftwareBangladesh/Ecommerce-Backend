# banner_api/services/banner.py
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from banner_api.models import Banner


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
def reorder_banners(*, banner_orders):
    """
    Reorder banners.

    banner_orders example:
        [
            {"id": 10, "display_order": 1},
            {"id": 15, "display_order": 2},
            {"id": 20, "display_order": 3},
        ]
    """
    banners = {
        banner.id: banner
        for banner in Banner.objects.filter(
            id__in=[item["id"] for item in banner_orders]
        )
    }

    for item in banner_orders:
        banner = banners.get(item["id"])

        if banner is None:
            continue

        banner.display_order = item["display_order"]
        banner.save(update_fields=["display_order", "updated_at"])

    return banners.values()
