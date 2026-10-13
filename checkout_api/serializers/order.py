# checkout_api/serializers/order.py
"""
Storefront order serializers.

These serializers are customer-facing. They do NOT
expose internal accounting, reservation, or
staff-only fields.
"""
from rest_framework import serializers


class OrderCreateSerializer(serializers.Serializer):
    """
    Input serializer for POST /checkout/confirm/.
    """
    shipping_address_id = serializers.IntegerField(
        required=True,
        help_text=(
            "ID of the customer's shipping address."
        ),
    )
    shipping_method_id = serializers.IntegerField(
        required=True,
        help_text=(
            "ID of the selected shipping method."
        ),
    )
    idempotency_key = serializers.CharField(
        required=True,
        max_length=255,
        help_text=(
            "Client-provided unique key for "
            "idempotent order creation."
        ),
    )
    notes = serializers.CharField(
        required=False,
        default='',
        allow_blank=True,
        help_text="Optional order notes.",
    )


class OrderItemVariantSerializer(
    serializers.Serializer
):
    id = serializers.IntegerField()
    sku = serializers.CharField()
    name = serializers.CharField(
        allow_blank=True, allow_null=True
    )


class OrderItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    product_variant = OrderItemVariantSerializer()
    product_name = serializers.CharField()
    quantity = serializers.IntegerField()
    unit_price = serializers.DecimalField(
        max_digits=15, decimal_places=2
    )
    line_total = serializers.DecimalField(
        max_digits=15, decimal_places=2
    )


class OrderPricingSerializer(serializers.Serializer):
    subtotal = serializers.DecimalField(
        max_digits=15, decimal_places=2
    )
    shipping_charge = serializers.DecimalField(
        max_digits=12, decimal_places=2
    )
    discount_total = serializers.DecimalField(
        max_digits=15, decimal_places=2
    )
    tax_total = serializers.DecimalField(
        max_digits=15, decimal_places=2
    )
    grand_total = serializers.DecimalField(
        max_digits=15, decimal_places=2
    )


class OrderShippingMethodSerializer(
    serializers.Serializer
):
    id = serializers.IntegerField()
    name = serializers.CharField()
    code = serializers.CharField()


class OrderShippingAddressSerializer(
    serializers.Serializer
):
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    company = serializers.CharField(
        allow_blank=True
    )
    address_1 = serializers.CharField()
    address_2 = serializers.CharField(
        allow_blank=True
    )
    city = serializers.CharField()
    state = serializers.CharField(
        allow_blank=True
    )
    postcode = serializers.CharField()
    country = serializers.CharField()
    phone = serializers.CharField(
        allow_blank=True
    )


class OrderCustomerSerializer(
    serializers.Serializer
):
    id = serializers.IntegerField()
    user = serializers.SerializerMethodField()

    def get_user(self, obj):
        return {
            'id': obj.user_id,
            'username': obj.user.username,
        }


class OrderDetailSerializer(serializers.Serializer):
    """
    Response serializer for order detail.
    Exposes approved fields only — no accounting
    internals, no reservation data, no staff-only
    fields.
    """
    id = serializers.IntegerField()
    invoice_number = serializers.CharField(
        allow_null=True
    )
    status = serializers.CharField()
    payment_status = serializers.CharField()
    channel = serializers.CharField()
    customer = OrderCustomerSerializer()
    items = serializers.SerializerMethodField()
    shipping_address = serializers.SerializerMethodField()
    pricing = serializers.SerializerMethodField()
    shipping_method = serializers.SerializerMethodField()
    notes = serializers.CharField(
        allow_blank=True, allow_null=True
    )
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    allowed_next_statuses = (
        serializers.SerializerMethodField()
    )

    def get_items(self, obj):
        sale_items = obj.items.select_related(
            'product_variant',
            'product_variant__product',
        ).all()
        result = []
        for item in sale_items:
            variant = item.product_variant
            result.append({
                'id': item.id,
                'product_variant': {
                    'id': variant.id,
                    'sku': variant.sku,
                    'name': variant.name,
                },
                'product_name': (
                    variant.product.name
                ),
                'quantity': item.quantity,
                'unit_price': item.unit_price,
                'line_total': item.line_total,
            })
        return result

    def get_shipping_address(self, obj):
        snapshot = (
            obj.shipping_address_snapshot or {}
        )
        return snapshot

    def get_shipping_method(self, obj):
        snapshot = obj.shipping_method_snapshot or {}
        if not snapshot:
            return None
        return snapshot

    def get_pricing(self, obj):
        return {
            'subtotal': obj.subtotal_amount,
            'shipping_charge': (
                obj.shipping_amount
            ),
            'discount_total': obj.discount_amount,
            'tax_total': obj.tax_amount,
            'grand_total': obj.total_amount,
        }

    def get_allowed_next_statuses(self, obj):
        from sale_api.models import (
            get_next_sale_statuses,
        )
        next_statuses = get_next_sale_statuses(
            obj.status
        )
        # Storefront customers cannot initiate returns;
        # return processing remains a staff/POS workflow.
        if obj.channel == 'Website':
            next_statuses = [
                status for status in next_statuses
                if status.value != 'RETURNED'
            ]
        return [
            {
                'value': status.value,
                'label': status.label,
            }
            for status in next_statuses
        ]


class OrderListSerializer(serializers.Serializer):
    """
    Compact serializer for order history list.
    """
    id = serializers.IntegerField()
    invoice_number = serializers.CharField(
        allow_null=True
    )
    status = serializers.CharField()
    payment_status = serializers.CharField()
    total_amount = serializers.DecimalField(
        max_digits=15, decimal_places=2
    )
    item_count = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()

    def get_item_count(self, obj):
        return obj.items.count()


class OrderCancelResponseSerializer(
    serializers.Serializer
):
    id = serializers.IntegerField()
    status = serializers.CharField()
    message = serializers.CharField()
