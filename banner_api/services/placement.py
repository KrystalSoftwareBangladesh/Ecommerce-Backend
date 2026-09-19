# banner_api/services/placement.py
from banner_api.models import BannerPlacement


def get_active_placements():
    return BannerPlacement.objects.filter(
        is_active=True,
    ).order_by("name")
