# banner_api/filters/banner.py
import django_filters

from banner_api.models import Banner


class BannerFilter(django_filters.FilterSet):
    placement = django_filters.NumberFilter(
        field_name="placement_id",
    )
    placement_code = django_filters.CharFilter(
        field_name="placement__code",
        lookup_expr="iexact",
    )

    class Meta:
        model = Banner
        fields = [
            "placement",
            "placement_code",
            "is_active",
        ]
