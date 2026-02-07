# supplier_api/serializers/suppier.py
from rest_framework import serializers

from supplier_api.models import Supplier, PaymentType
from category_api.models import Category


ALLOWED_CREDIT_DAYS = {15, 30, 45}


class SupplierListSerializer(serializers.ModelSerializer):
    categories = serializers.StringRelatedField(many=True)

    class Meta:
        model = Supplier
        fields = [
            'id', 'name', 'contact_person', 'phone', 'email',
            'payment_type', 'credit_days', 'categories'
        ]


class SupplierDetailSerializer(serializers.ModelSerializer):
    categories = serializers.StringRelatedField(many=True)
    created_by = serializers.StringRelatedField()
    updated_by = serializers.StringRelatedField()

    class Meta:
        model = Supplier
        fields = '__all__'
        read_only_fields = [
            'created_by', 'updated_by', 'created_at', 'updated_at',
            'is_active', 'deleted_at',
        ]


class SupplierCreateUpdateSerializer(serializers.ModelSerializer):
    categories = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Category.objects.all(),
        required=False
    )

    class Meta:
        model = Supplier
        fields = [
            'id', 'name', 'contact_person', 'phone', 'email', 'address',
            'notes', 'payment_type', 'credit_days', 'categories'
        ]

    def validate(self, attrs):
        # Name uniqueness (global, single-company MVP)
        instance_name = self.instance.name if self.instance else None
        name = attrs.get('name', instance_name)
        if name:
            queryset = Supplier.objects.filter(
                name__iexact=name, is_active=True)
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise serializers.ValidationError({
                    'name': 'A supplier with this name already exists.'
                })

        # Payment type + credit_days logic (handles partial updates)
        instance_payment_type = self.instance.payment_type if self.instance else None   # noqa
        payment_type = attrs.get('payment_type', instance_payment_type)

        instance_credit_days = self.instance.credit_days if self.instance else None     # noqa
        credit_days = attrs.get('credit_days', instance_credit_days)

        if payment_type == PaymentType.CREDIT:
            if credit_days is None:
                raise serializers.ValidationError({
                    'credit_days': 'Credit days is required for CREDIT payment type.'   # noqa
                })
            if credit_days not in ALLOWED_CREDIT_DAYS:
                raise serializers.ValidationError({
                    'credit_days': 'Credit days must be 15, 30, or 45.'
                })
        elif credit_days is not None:
            raise serializers.ValidationError({
                'credit_days': 'Credit days can only be set for CREDIT payment type.'   # noqa
            })

        return attrs
