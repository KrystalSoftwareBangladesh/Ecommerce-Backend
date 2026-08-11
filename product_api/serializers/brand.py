# product_api/serializers/brand.py
from rest_framework import serializers

from product_api.services import BrandService

from product_api.models import Brand


class BrandListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing brands (read-only).
    """
    class Meta:
        model = Brand
        fields = [
            'id',
            'name',
            'slug',
            'display_order',
            'is_active',
            'created_at',
        ]
        read_only_fields = [
            'id',
            'created_at',
        ]


class BrandDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for brand detail view.
    Includes all fields and metadata.
    """
    created_by = serializers.StringRelatedField(read_only=True)
    updated_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Brand
        fields = [
            'id',
            'name',
            'slug',
            'description',
            'display_order',
            'is_active',
            'created_at',
            'updated_at',
            'created_by',
            'updated_by',
        ]
        read_only_fields = [
            'id',
            'created_at',
            'updated_at',
            'created_by',
            'updated_by',
        ]


class BrandCreateUpdateSerializer(serializers.ModelSerializer):
    display_order = serializers.IntegerField(
        required=False,
        min_value=1,
    )
    slug = serializers.CharField(
        required=False,
        allow_blank=True
    )

    class Meta:
        model = Brand
        fields = [
            'id',
            'name',
            'slug',
            'description',
            'display_order',
            'is_active',
        ]
        read_only_fields = [
            'id', 'is_active',
        ]

    def validate_name(self, value):
        qs = Brand.objects.filter(name__iexact=value)

        # Exclude current instance when updating
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise serializers.ValidationError(
                "A brand with this name already exists."
            )
        return value

    def validate(self, attrs):
        instance = self.instance

        if instance and 'slug' in attrs and attrs['slug']:
            raise serializers.ValidationError(
                {'slug': 'Slug cannot be updated once created.'}
            )

        return attrs

    def create(self, validated_data):
        return BrandService.create_brand(
            validated_data=validated_data,
            user=self.context["request"].user,
        )

    def update(self, instance, validated_data):
        return BrandService.update_brand(
            instance=instance,
            validated_data=validated_data,
            user=self.context["request"].user,
        )
