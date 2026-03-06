# sale_api/serializers/sale.py
from rest_framework import serializers

from product_api.models import ProductVariant
from sale_api.models import Sale, SaleItem
from customer_api.serializers import CustomerProfileDetailSerializer
from product_api.serializers import ProductVariantDetailSerializer


class SaleItemSerializer(serializers.ModelSerializer):
    product_variant = ProductVariantDetailSerializer(read_only=True)
    product_variant_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.all(),
        source='product_variant',
        write_only=True,
    )

    class Meta:
        model = SaleItem
        fields = ['id', 'product_variant', 'product_variant_id',
                  'quantity', 'unit_price', 'line_total']
        read_only_fields = ['line_total']

    def validate(self, data):
        if data['quantity'] <= 0:
            raise serializers.ValidationError(
                {'quantity': 'Must be positive.'})
        if data['unit_price'] < 0:
            raise serializers.ValidationError(
                {'unit_price': 'Must be non-negative.'})
        return data


class SaleCreateSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True)

    class Meta:
        model = Sale
        fields = ['customer', 'sale_date', 'invoice_number', 'channel',
                  'discount_amount', 'tax_amount', 'notes', 'items']

    def validate(self, data):
        if not data.get('items'):
            raise serializers.ValidationError('At least one item is required.')
        variants = set()
        for item in data['items']:
            if item['product_variant'] in variants:
                raise serializers.ValidationError('Duplicate product variant.')
            variants.add(item['product_variant'])
        return data


class SaleUpdateSerializer(SaleCreateSerializer):
    pass  # Same as create for simplicity


class SaleListSerializer(serializers.ModelSerializer):
    customer = CustomerProfileDetailSerializer()

    class Meta:
        model = Sale
        fields = ['id', 'customer', 'sale_date',
                  'invoice_number', 'channel', 'status', 'total_amount']


class SaleDetailSerializer(serializers.ModelSerializer):
    customer = CustomerProfileDetailSerializer()
    items = SaleItemSerializer(many=True)

    class Meta:
        model = Sale
        fields = '__all__'


class SaleChannelOptionSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class SaleChannelListSerializer(serializers.Serializer):
    default = serializers.ChoiceField(choices=Sale.SaleChannel.choices)
    channels = SaleChannelOptionSerializer(many=True)
