# banner_api/serializers/banner.py
from rest_framework import serializers

from banner_api.models import Banner


class BannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banner
        fields = [
            "id",
            "placement",
            "title",
            "subtitle",
            "image",
            "mobile_image",
            "cta_text",
            "cta_url",
            "display_order",
            "is_active",
            "start_at",
            "end_at",
            "deleted_at",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "deleted_at",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        start_at = attrs.get("start_at")
        end_at = attrs.get("end_at")

        # When updating, use existing values if they weren't supplied.
        if self.instance:
            start_at = (
                start_at
                if start_at is not None
                else self.instance.start_at
            )
            end_at = (
                end_at
                if end_at is not None
                else self.instance.end_at
            )

        if start_at and end_at and start_at >= end_at:
            raise serializers.ValidationError({
                "end_at": "End time must be later than start time."
            })

        return attrs


class BannerStorefrontSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banner
        fields = [
            "id",
            "title",
            "subtitle",
            "image",
            "mobile_image",
            "cta_text",
            "cta_url",
            "display_order",
        ]


class BannerReorderItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    display_order = serializers.IntegerField(min_value=0)


class BannerReorderSerializer(serializers.Serializer):
    banners = BannerReorderItemSerializer(many=True, allow_empty=False)


class ReorderBannerResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()
