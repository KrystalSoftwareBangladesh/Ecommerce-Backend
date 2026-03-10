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
        ]
        read_only_fields = ['id']

    def validate_code(self, value):
        queryset = ChartOfAccount.objects.filter(
            code__iexact=value,
            deleted_at__isnull=True,
        )
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                'An account with this code already exists.'
            )
        return value

    def validate_parent(self, value):
        if value and not value.is_active:
            raise serializers.ValidationError(
                'Inactive parent account cannot be assigned.'
            )
        return value

    def validate(self, attrs):
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
