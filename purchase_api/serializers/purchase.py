# purchase_api/serializers/purchase.py
from rest_framework import serializers
# from django.db.models import Sum, F
from drf_writable_nested import WritableNestedModelSerializer

from product_api.models import ProductVariant
from purchase_api.models import Purchase, PurchaseItem, PurchaseStatus
from supplier_api.serializers import SupplierListSerializer
from product_api.serializers import ProductVariantDetailSerializer as VariantSerializer   # noqa


class PurchaseItemSerializer(serializers.ModelSerializer):
    product_variant = VariantSerializer(read_only=True)
    product_variant_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.filter(is_active=True),
        source='product_variant',
        write_only=True
    )

    class Meta:
        model = PurchaseItem
        fields = ['id', 'product_variant', 'product_variant_id',
                  'quantity', 'unit_cost', 'line_total']
        read_only_fields = ['line_total']

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be positive.")
        return value

    def validate_unit_cost(self, value):
        if value < 0:
            raise serializers.ValidationError("Unit cost cannot be negative.")
        return value


class PurchaseListSerializer(serializers.ModelSerializer):
    supplier = SupplierListSerializer()

    class Meta:
        model = Purchase
        fields = ['id', 'supplier', 'purchase_date',
                  'invoice_number', 'status', 'total_amount']


class PurchaseDetailSerializer(serializers.ModelSerializer):
    supplier = SupplierListSerializer()
    items = PurchaseItemSerializer(many=True)

    class Meta:
        model = Purchase
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at',
                            'created_by', 'updated_by', 'is_active']


class PurchaseCreateSerializer(WritableNestedModelSerializer):
    items = PurchaseItemSerializer(many=True)

    class Meta:
        model = Purchase
        fields = [
            'id', 'supplier', 'purchase_date', 'invoice_number',
            'discount_amount', 'tax_amount', 'notes', 'items',
        ]

    def validate(self, attrs):
        if not attrs.get('items'):
            raise serializers.ValidationError(
                {"items": "At least one item is required."})
        return attrs


class PurchaseUpdateSerializer(serializers.ModelSerializer):
    items = PurchaseItemSerializer(many=True, required=False)

    class Meta:
        model = Purchase
        fields = [
            'supplier', 'purchase_date', 'invoice_number', 'discount_amount',
            'tax_amount', 'notes', 'items', 'status'
        ]
        extra_kwargs = {
            'status': {'read_only': True}
        }

    def validate(self, attrs):
        instance = self.instance
        if instance.status != PurchaseStatus.DRAFT:
            allowed_fields = {'discount_amount', 'tax_amount', 'notes'}
            for field in attrs:
                if field not in allowed_fields and field != 'items':
                    raise serializers.ValidationError(
                        f"Cannot edit {field} for non-draft purchase.")
            if 'items' in attrs:
                raise serializers.ValidationError(
                    "Cannot edit items for non-draft purchase.")
        if 'items' in attrs and not attrs['items']:
            raise serializers.ValidationError(
                {"items": "At least one item is required."})
        return attrs
