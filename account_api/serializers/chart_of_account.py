from rest_framework import serializers

from account_api.models import ChartOfAccount


class ChartOfAccountListSerializer(serializers.ModelSerializer):
    parent = serializers.StringRelatedField()

    class Meta:
        model = ChartOfAccount
        fields = [
            'id',
            'code',
            'name',
            'account_type',
            'parent',
            'opening_balance',
            'opening_date',
            'is_active',
        ]


class ChartOfAccountDetailSerializer(serializers.ModelSerializer):
    parent = serializers.StringRelatedField()
    created_by = serializers.StringRelatedField()
    updated_by = serializers.StringRelatedField()

    class Meta:
        model = ChartOfAccount
        fields = '__all__'
        read_only_fields = [
            'created_by',
            'updated_by',
            'created_at',
            'updated_at',
            'is_active',
            'deleted_at',
        ]


class ChartOfAccountCreateUpdateSerializer(serializers.ModelSerializer):
    parent = serializers.PrimaryKeyRelatedField(
        queryset=ChartOfAccount.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
        ),
        required=False,
        allow_null=True,
    )
    opening_balance = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        write_only=True,
    )
    opening_date = serializers.DateField(
        required=False,
        write_only=True,
    )
    opening_contra_account_id = serializers.PrimaryKeyRelatedField(
        queryset=ChartOfAccount.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
        ),
        source='opening_contra_account',
        required=False,
        allow_null=True,
        write_only=True,
    )

    class Meta:
        model = ChartOfAccount
        fields = [
            'id',
            'code',
            'name',
            'account_type',
            'description',
            'parent',
            'is_active',
            'opening_balance',
            'opening_date',
            'opening_contra_account_id',
        ]
        read_only_fields = ['id', 'code']

    def validate_parent(self, value):
        if value and not value.is_active:
            raise serializers.ValidationError(
                'Inactive parent account cannot be assigned.'
            )
        return value

    def validate(self, attrs):
        if 'code' in self.initial_data:
            raise serializers.ValidationError({
                'code': 'Account code is generated automatically.'
            })

        opening_balance = attrs.get('opening_balance')
        opening_date = attrs.get('opening_date')
        opening_fields_present = (
            'opening_balance' in attrs
            or 'opening_date' in attrs
            or 'opening_contra_account' in attrs
        )

        if self.instance and opening_fields_present:
            raise serializers.ValidationError({
                'detail': (
                    'Use the set-opening-balance action to manage '
                    'opening balances after the account has been '
                    'created.'
                )
            })

        if opening_balance is not None and opening_date is None:
            raise serializers.ValidationError({
                'opening_date': (
                    'Opening date is required when an opening '
                    'balance is provided.'
                )
            })

        if opening_date is not None and opening_balance is None:
            raise serializers.ValidationError({
                'opening_balance': (
                    'Opening balance amount is required when an '
                    'opening date is provided.'
                )
            })

        parent = attrs.get('parent', getattr(self.instance, 'parent', None))
        account_type = attrs.get(
            'account_type',
            getattr(self.instance, 'account_type', None),
        )

        if parent and parent.account_type != account_type:
            raise serializers.ValidationError({
                'parent': 'Parent account must have the same account type.'
            })

        if self.instance and parent and parent.pk == self.instance.pk:
            raise serializers.ValidationError({
                'parent': 'An account cannot be its own parent.'
            })

        if self.instance and parent:
            current_parent = parent
            while current_parent:
                if current_parent.pk == self.instance.pk:
                    raise serializers.ValidationError({
                        'parent': (
                            'Circular parent relationship is not allowed.'
                        )
                    })
                current_parent = current_parent.parent

        return attrs


class ChartOfAccountOpeningBalanceSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    date = serializers.DateField()
    contra_account_id = serializers.PrimaryKeyRelatedField(
        queryset=ChartOfAccount.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
        ),
        source='contra_account',
        required=False,
        allow_null=True,
    )
