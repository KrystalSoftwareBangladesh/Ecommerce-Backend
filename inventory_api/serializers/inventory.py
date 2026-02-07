# inventory_api/serializers/inventory.py
from rest_framework import serializers

from product_api.models import ProductVariant
from inventory_api.models import InventoryMovement


class InventoryMovementSerializer(serializers.ModelSerializer):
    created_by = serializers.StringRelatedField(read_only=True)
    product_variant = serializers.StringRelatedField(read_only=True)
    product_variant_id = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.all(),
        source='product_variant',
        write_only=True
    )

    class Meta:
        model = InventoryMovement
        fields = '__all__'
        read_only_fields = ['created_at', 'created_by']
