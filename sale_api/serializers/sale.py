# sale_api/serializers/sale.py
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from account_api.models import AccountType, ChartOfAccount
from product_api.models import ProductVariant
from sale_api.models import (
    PaymentMethod,
    Sale,
    SaleItem,
    SaleStatus,
    get_next_sale_statuses,
)
from customer_api.serializers import CustomerProfileDetailSerializer
from product_api.serializers import ProductVariantDetailSerializer


class SaleAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChartOfAccount
        fields = ['id', 'code', 'name', 'account_type']


class SaleTransactionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    transaction_no = serializers.CharField()
    transaction_type = serializers.CharField()
    status = serializers.CharField()
    reference = serializers.CharField(allow_null=True)


class SalePaymentMethodSerializer(serializers.ModelSerializer):
    default_account = SaleAccountSerializer(read_only=True)

    class Meta:
        model = PaymentMethod
        fields = [
            'id',
            'code',
            'name',
            'allow_account_override',
            'default_account_id',
            'default_account',
        ]


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
    payment_method_id = serializers.PrimaryKeyRelatedField(
        queryset=PaymentMethod.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
        ),
        source='payment_method',
        required=False,
        allow_null=True,
    )
    account_id = serializers.PrimaryKeyRelatedField(
        queryset=ChartOfAccount.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
        ),
        source='account',
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Sale
        fields = [
            'customer', 'payment_method_id', 'account_id', 'sale_date',
            'invoice_number', 'channel', 'discount_amount', 'tax_amount',
            'notes', 'items',
        ]

    def validate(self, data):
        if not data.get('items'):
            raise serializers.ValidationError('At least one item is required.')
        variants = set()
        for item in data['items']:
            if item['product_variant'] in variants:
                raise serializers.ValidationError('Duplicate product variant.')
            variants.add(item['product_variant'])
        account = data.get('account')
        if account and account.account_type != AccountType.ASSET:
            raise serializers.ValidationError({
                'account_id': (
                    'Sale account must be an asset account.'
                )
            })
        return data


class SaleUpdateSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True, required=False)
    status = serializers.ChoiceField(
        choices=SaleStatus.choices,
        required=False,
    )
    payment_method_id = serializers.PrimaryKeyRelatedField(
        queryset=PaymentMethod.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
        ),
        source='payment_method',
        required=False,
        allow_null=True,
    )
    account_id = serializers.PrimaryKeyRelatedField(
        queryset=ChartOfAccount.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
        ),
        source='account',
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Sale
        fields = [
            'customer', 'payment_method_id', 'account_id', 'sale_date',
            'channel', 'discount_amount', 'tax_amount', 'notes', 'items',
            'status',
        ]

    def validate(self, data):
        items = data.get('items')
        account = data.get('account', getattr(self.instance, 'account', None))
        if account and account.account_type != AccountType.ASSET:
            raise serializers.ValidationError({
                'account_id': 'Sale account must be an asset account.'
            })
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
    payment_method = SalePaymentMethodSerializer(read_only=True)
    account = SaleAccountSerializer(read_only=True)
    accounting_transaction = SaleTransactionSerializer(read_only=True)

    class Meta:
        model = Sale
        fields = [
            'id', 'customer', 'payment_method', 'account', 'sale_date',
            'invoice_number', 'channel', 'status', 'total_amount',
            'accounting_transaction',
        ]


class SaleStatusOptionSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class SaleDetailSerializer(serializers.ModelSerializer):
    customer = CustomerProfileDetailSerializer()
    items = SaleItemSerializer(many=True)
    allowed_next_statuses = serializers.SerializerMethodField()
    payment_method = SalePaymentMethodSerializer(read_only=True)
    account = SaleAccountSerializer(read_only=True)
    accounting_transaction = SaleTransactionSerializer(read_only=True)
    return_transaction = SaleTransactionSerializer(read_only=True)

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
    payment_method_id = serializers.PrimaryKeyRelatedField(
        queryset=PaymentMethod.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
        ),
        source='payment_method',
        required=False,
        allow_null=True,
    )
    account_id = serializers.PrimaryKeyRelatedField(
        queryset=ChartOfAccount.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
        ),
        source='account',
        required=False,
        allow_null=True,
    )

    def validate_account(self, value):
        if value and value.account_type != AccountType.ASSET:
            raise serializers.ValidationError(
                'Sale account must be an asset account.'
            )
        return value
