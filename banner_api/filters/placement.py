# banner_api/filters/placement.py
import django_filters

from banner_api.models import BannerPlacement


class BannerPlacementFilter(django_filters.FilterSet):
    class Meta:
        model = BannerPlacement
        fields = [
            "is_active",
        ]
