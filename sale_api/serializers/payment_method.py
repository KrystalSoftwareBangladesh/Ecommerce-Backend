from rest_framework import serializers

from account_api.models import AccountType, ChartOfAccount
from sale_api.models import PaymentMethod


class PaymentMethodAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChartOfAccount
        fields = ['id', 'code', 'name', 'account_type']


class PaymentMethodListSerializer(serializers.ModelSerializer):
    default_account = PaymentMethodAccountSerializer(read_only=True)

    class Meta:
        model = PaymentMethod
        fields = [
            'id',
            'code',
            'name',
            'description',
            'is_active',
            'sort_order',
            'allow_account_override',
            'default_account_id',
            'default_account',
        ]


class PaymentMethodDetailSerializer(serializers.ModelSerializer):
    default_account = PaymentMethodAccountSerializer(read_only=True)
    created_by = serializers.StringRelatedField()
    updated_by = serializers.StringRelatedField()

    class Meta:
        model = PaymentMethod
        fields = '__all__'
        read_only_fields = [
            'created_at',
            'updated_at',
            'created_by',
            'updated_by',
            'deleted_at',
        ]


class PaymentMethodCreateUpdateSerializer(serializers.ModelSerializer):
    default_account_id = serializers.PrimaryKeyRelatedField(
        queryset=ChartOfAccount.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
        ),
        source='default_account',
        required=False,
        allow_null=True,
    )

    class Meta:
        model = PaymentMethod
        fields = [
            'id',
            'code',
            'name',
            'description',
            'is_active',
            'sort_order',
            'allow_account_override',
            'default_account_id',
        ]
        read_only_fields = ['id']

    def validate_default_account(self, value):
        if value is None:
            return value

        if value.account_type != AccountType.ASSET:
            raise serializers.ValidationError(
                'Default account must be an asset account.'
            )
        return value
