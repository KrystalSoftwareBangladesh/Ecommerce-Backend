# product_api/serializers/product_image.py
from PIL import Image, UnidentifiedImageError
from rest_framework import serializers

from EcommerceBackend.core.serializers.fields import (
    AbsoluteImageField,
)
from product_api.models import Product, ProductImage
from product_api.services.product import set_product_image_default


class ProductDefaultImageSerializer(serializers.Serializer):
    """Lightweight serializer for a product's default image."""
    id = serializers.IntegerField(read_only=True)
    image = AbsoluteImageField(read_only=True)
    alt_text = serializers.CharField(read_only=True)
    display_order = serializers.IntegerField(read_only=True)
    is_default = serializers.BooleanField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)

    def to_representation(self, instance):
        if instance is None:
            return None
        return super().to_representation(instance)


class ProductImageListSerializer(serializers.ModelSerializer):
    """Serializer for listing product images."""
    image = AbsoluteImageField(read_only=True)

    class Meta:
        model = ProductImage
        fields = [
            'id',
            'image',
            'alt_text',
            'display_order',
            'is_default',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class ProductImageDetailSerializer(serializers.ModelSerializer):
    """Serializer for full product image details."""
    product = serializers.StringRelatedField(read_only=True)
    image = AbsoluteImageField(read_only=True)
    created_by = serializers.StringRelatedField(read_only=True)
    updated_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = ProductImage
        fields = [
            'id',
            'product',
            'image',
            'alt_text',
            'display_order',
            'is_default',
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


class ProductImageCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating product image metadata."""
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True),
        required=False
    )

    class Meta:
        model = ProductImage
        fields = [
            'id',
            'product',
            'image',
            'alt_text',
            'display_order',
            'is_default',
        ]
        extra_kwargs = {
            'id': {'read_only': True},
        }

    def validate_image(self, value):
        """Validate that the uploaded file is a supported image."""
        if value is None:
            return value

        max_size = 1024 * 1024
        if getattr(value, 'size', None) is not None and value.size > max_size:
            raise serializers.ValidationError(
                'Image size must be 1 MB or less.'
            )

        extension = value.name.lower().rsplit('.', 1)[-1] if value.name else ''
        allowed_extensions = {'jpg', 'jpeg', 'png', 'webp'}
        if extension not in allowed_extensions:
            raise serializers.ValidationError(
                'Unsupported image format. Allowed formats are '
                'jpg, jpeg, png, and webp.'
            )

        try:
            with Image.open(value) as image_file:
                image_format = image_file.format
                image_file.verify()
        except (UnidentifiedImageError, OSError):
            raise serializers.ValidationError(
                'Uploaded file is not a valid image.'
            )

        if image_format is None:
            raise serializers.ValidationError(
                'Uploaded file is not a valid image.'
            )

        normalized_format = image_format.lower()
        if normalized_format not in {'jpeg', 'png', 'webp', 'jpg'}:
            raise serializers.ValidationError(
                'Unsupported image format. Allowed formats are '
                'jpg, jpeg, png, and webp.'
            )

        value.seek(0)
        return value

    def update(self, instance, validated_data):
        if validated_data.get('is_default'):
            set_product_image_default(
                instance,
                updated_by=self.context['request'].user,
            )
            validated_data.pop('is_default')
        return super().update(instance, validated_data)


class BulkProductImageItemSerializer(serializers.Serializer):
    image = serializers.ImageField()
    alt_text = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
    )
    display_order = serializers.IntegerField(
        required=False,
        min_value=0,
    )
    is_default = serializers.BooleanField(
        required=False,
        default=False,
    )

    def validate_image(self, value):
        return ProductImageCreateUpdateSerializer().validate_image(value)


class BulkProductImageUploadSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True),
    )

    images = BulkProductImageItemSerializer(
        many=True,
        min_length=1,
        max_length=10,
    )

    def validate(self, attrs):
        images = attrs["images"]

        default_count = sum(
            1
            for image in images
            if image.get("is_default", False)
        )

        if default_count > 1:
            raise serializers.ValidationError(
                {
                    "images": (
                        "Only one image can be marked as the default."
                    )
                }
            )

        return attrs
