# banner_api/serializers/placement.py
from rest_framework import serializers

from banner_api.models import BannerPlacement


class BannerPlacementSerializer(serializers.ModelSerializer):
    class Meta:
        model = BannerPlacement
        fields = [
            "id",
            "name",
            "code",
            "description",
            "is_active",
            "deleted_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "deleted_at",
            "created_at",
            "updated_at",
        ]
