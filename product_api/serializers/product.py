# product_api/serializers/product.py
from rest_framework import serializers
# from django.db.models import Sum, Value
# from django.db.models.functions import Coalesce

# from category_api.models import Category
from product_api.models import (
    Product, ProductPriceHistory, ProductVariant,
    # InventoryMovement, MovementType
)


class ProductPriceHistorySerializer(serializers.ModelSerializer):
    changed_by = serializers.StringRelatedField()

    class Meta:
        model = ProductPriceHistory
        fields = ['price', 'changed_at', 'changed_by']


class ProductListSerializer(serializers.ModelSerializer):
    category = serializers.StringRelatedField()

    class Meta:
        model = Product
        fields = ['id', 'name', 'category', 'current_selling_price']


class ProductDetailSerializer(serializers.ModelSerializer):
    category = serializers.StringRelatedField()
    price_histories = ProductPriceHistorySerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'is_active']


class ProductCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'name', 'category', 'current_selling_price']

    def validate_name(self, value):
        qs = Product.objects.filter(name__iexact=value, is_active=True)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "A product with this name already exists.")
        return value

    def create(self, validated_data):
        instance = super().create(validated_data)
        ProductPriceHistory.objects.create(
            product=instance,
            price=instance.current_selling_price,
            changed_by=self.context['request'].user
        )
        return instance

    def update(self, instance, validated_data):
        old_price = instance.current_selling_price
        instance = super().update(instance, validated_data)
        new_price = instance.current_selling_price
        if old_price != new_price:
            ProductPriceHistory.objects.create(
                product=instance,
                price=new_price,
                changed_by=self.context['request'].user
            )
        return instance


class ProductVariantListSerializer(serializers.ModelSerializer):
    product = serializers.StringRelatedField()
    current_stock = serializers.IntegerField(read_only=True)

    class Meta:
        model = ProductVariant
        fields = ['id', 'product', 'sku', 'color', 'size', 'current_stock']


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
        fields = ['id', 'product', 'sku', 'color', 'size']

    def validate_sku(self, value):
        qs = ProductVariant.objects.filter(sku__exact=value, is_active=True)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "A variant with this SKU already exists.")
        return value


# class InventoryMovementSerializer(serializers.ModelSerializer):
#     created_by = serializers.StringRelatedField(read_only=True)
#     product_variant = serializers.StringRelatedField(read_only=True)
#     product_variant_id = serializers.PrimaryKeyRelatedField(
#         queryset=ProductVariant.objects.all(),
#         source='product_variant',
#         write_only=True
#     )

#     class Meta:
#         model = InventoryMovement
#         fields = '__all__'
#         read_only_fields = ['created_at', 'created_by']
