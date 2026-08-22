# product_api/serializers/product.py
from drf_spectacular.utils import extend_schema_field

from rest_framework import serializers

from category_api.models import Category
from origin_api.models import Origin
from product_api.models import (
    Product, ProductPriceHistory, ProductVariant,
)
from category_api.serializers import CategorySummarySerializer
from product_api.serializers.product_image import ProductDefaultImageSerializer
from origin_api.serializers import OriginSummarySerializer


class ProductVariantSerializer(serializers.ModelSerializer):
    """Serializer for ProductVariant - used for nested creation"""
    class Meta:
        model = ProductVariant
        fields = ['id', 'name', 'sku', 'color', 'size']
        extra_kwargs = {
            'id': {'read_only': True}
        }

    def validate_sku(self, value):
        """Validate SKU uniqueness"""
        qs = ProductVariant.objects.filter(sku__iexact=value, is_active=True)

        # If we're updating, exclude the current instance
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if hasattr(self, 'parent') and hasattr(self.parent, 'instance'):
            qs = qs.exclude(product=self.parent.instance)

        if qs.exists():
            raise serializers.ValidationError(
                "A variant with this SKU already exists."
            )
        return value


class ProductPriceHistorySerializer(serializers.ModelSerializer):
    changed_by = serializers.StringRelatedField()

    class Meta:
        model = ProductPriceHistory
        fields = ['price', 'changed_at', 'changed_by']


class ProductListSerializer(serializers.ModelSerializer):
    default_image = serializers.SerializerMethodField()
    origin = OriginSummarySerializer(read_only=True)
    average_rating = serializers.FloatField(read_only=True)
    total_reviews = serializers.IntegerField(read_only=True)
    wishlist = serializers.BooleanField(read_only=True)
    in_cart = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug', 'current_selling_price', 'default_image',
            'origin', "average_rating", "total_reviews", "wishlist", "in_cart",
        ]

    @extend_schema_field(ProductDefaultImageSerializer)
    def get_default_image(self, obj):
        default_images = getattr(obj, '_default_images', [])
        if not default_images:
            return None
        return ProductDefaultImageSerializer(default_images[0]).data


class ProductDetailSerializer(serializers.ModelSerializer):
    categories = CategorySummarySerializer(many=True)
    origin = OriginSummarySerializer(read_only=True)
    price_histories = ProductPriceHistorySerializer(many=True, read_only=True)
    wishlist = serializers.BooleanField(read_only=True)
    in_cart = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = '__all__'
        read_only_fields = [
            'created_at',
            'updated_at',
            'is_active',
            'wishlist',
            'in_cart',
        ]


class ProductCreateUpdateSerializer(serializers.ModelSerializer):
    variants = ProductVariantSerializer(many=True, required=False)
    categories = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.filter(is_active=True),
        many=True,
        required=False
    )
    origin = serializers.PrimaryKeyRelatedField(
        queryset=Origin.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'categories', 'origin', 'current_selling_price',
            'variants',
        ]
        extra_kwargs = {
            'id': {'read_only': True}
        }

    def validate_name(self, value):
        qs = Product.objects.filter(name__iexact=value, is_active=True)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "A product with this name already exists.")
        return value

    def create(self, validated_data):
        variants_data = validated_data.pop('variants', [])
        categories = validated_data.pop('categories', [])
        product = Product.objects.create(**validated_data)

        if categories:
            product.categories.set(categories)

        ProductPriceHistory.objects.create(
            product=product,
            price=product.current_selling_price,
            changed_by=self.context['request'].user
        )

        if variants_data:
            variants_to_create = []
            for variant_data in variants_data:
                variants_to_create.append(
                    ProductVariant(product=product, **variant_data)
                )
            ProductVariant.objects.bulk_create(variants_to_create)

        return product

    def update(self, instance, validated_data):
        old_price = instance.current_selling_price
        categories = validated_data.pop('categories', None)
        instance = super().update(instance, validated_data)

        if categories is not None:
            instance.categories.set(categories)

        new_price = instance.current_selling_price
        if old_price != new_price:
            ProductPriceHistory.objects.create(
                product=instance,
                price=new_price,
                changed_by=self.context['request'].user
            )

        return instance

    def to_representation(self, instance):
        """Customize the output representation"""
        representation = super().to_representation(instance)

        # Include only active variants in the response
        if instance.pk:
            active_variants = instance.variants.filter(is_active=True)
            representation['variants'] = ProductVariantSerializer(
                active_variants, many=True
            ).data

        return representation


class ProductVariantListSerializer(serializers.ModelSerializer):
    product = serializers.StringRelatedField()
    current_stock = serializers.IntegerField(read_only=True)

    class Meta:
        model = ProductVariant
        fields = [
            'id', 'product', 'name', 'sku', 'color', 'size', 'current_stock'
        ]


class ProductVariantDetailSerializer(serializers.ModelSerializer):
    product = serializers.StringRelatedField()
    current_stock = serializers.IntegerField(read_only=True)

    class Meta:
        model = ProductVariant
        fields = '__all__'
        read_only_fields = ['created_at',
                            'updated_at', 'is_active', 'current_stock']


class ProductVariantCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = ['id', 'product', 'name', 'sku', 'color', 'size']

    def validate_sku(self, value):
        qs = ProductVariant.objects.filter(sku__exact=value, is_active=True)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "A variant with this SKU already exists.")
        return value
