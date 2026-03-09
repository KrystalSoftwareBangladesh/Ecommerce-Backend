# sale_api/serializers/sale.py
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from product_api.models import ProductVariant
from sale_api.models import Sale, SaleItem, SaleStatus, get_next_sale_statuses
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


class SaleUpdateSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True, required=False)
    status = serializers.ChoiceField(
        choices=SaleStatus.choices,
        required=False,
    )

    class Meta:
        model = Sale
        fields = ['customer', 'sale_date', 'channel', 'discount_amount',
                  'tax_amount', 'notes', 'items', 'status']

    def validate(self, data):
        items = data.get('items')
        if items is None:
            return data

        variants = set()
        for item in items:
            if item['product_variant'] in variants:
                raise serializers.ValidationError('Duplicate product variant.')
            variants.add(item['product_variant'])
        return data


class SaleListSerializer(serializers.ModelSerializer):
    customer = CustomerProfileDetailSerializer()

    class Meta:
        model = Sale
        fields = ['id', 'customer', 'sale_date',
                  'invoice_number', 'channel', 'status', 'total_amount']


class SaleStatusOptionSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class SaleDetailSerializer(serializers.ModelSerializer):
    customer = CustomerProfileDetailSerializer()
    items = SaleItemSerializer(many=True)
    allowed_next_statuses = serializers.SerializerMethodField()

    class Meta:
        model = Sale
        fields = '__all__'

    @extend_schema_field(SaleStatusOptionSerializer(many=True))
    def get_allowed_next_statuses(self, obj):
        return [
            {'value': value, 'label': SaleStatus(value).label}
            for value in get_next_sale_statuses(obj.status)
        ]


class SaleChannelOptionSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class SaleChannelListSerializer(serializers.Serializer):
    default = serializers.CharField()
    channels = SaleChannelOptionSerializer(many=True)


class SaleStatusListSerializer(serializers.Serializer):
    default = serializers.CharField()
    statuses = SaleStatusOptionSerializer(many=True)
    transitions = serializers.DictField(
        child=serializers.ListField(
            child=serializers.ChoiceField(choices=SaleStatus.choices)
        )
    )


class SaleStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=SaleStatus.choices)
