# customer_api/serializers/customer_address.py
from rest_framework import serializers

from customer_api.models import CustomerAddress
from shipping_api.models import ShippingZone


class CustomerAddressListSerializer(serializers.ModelSerializer):
    shipping_zone_name = serializers.CharField(
        source="shipping_zone.name",
        read_only=True,
        default=None,
    )

    class Meta:
        model = CustomerAddress
        fields = [
            "id",
            "address_type",
            "first_name",
            "last_name",
            "phone",
            "address_1",
            "address_2",
            "city",
            "state",
            "postcode",
            "country",
            "shipping_zone",
            "shipping_zone_name",
            "created_at",
        ]


class CustomerAddressDetailSerializer(serializers.ModelSerializer):
    shipping_zone_name = serializers.CharField(
        source="shipping_zone.name",
        read_only=True,
        default=None,
    )
    shipping_zone_code = serializers.CharField(
        source="shipping_zone.code",
        read_only=True,
        default=None,
    )

    class Meta:
        model = CustomerAddress
        fields = [
            "id",
            "address_type",
            "first_name",
            "last_name",
            "company",
            "address_1",
            "address_2",
            "city",
            "state",
            "postcode",
            "country",
            "phone",
            "shipping_zone",
            "shipping_zone_name",
            "shipping_zone_code",
            "created_at",
            "updated_at",
        ]


class CustomerAddressCreateUpdateSerializer(serializers.ModelSerializer):
    shipping_zone = serializers.PrimaryKeyRelatedField(
        queryset=ShippingZone.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
        ),
        required=False,
        allow_null=True,
        help_text=(
            "Active shipping zone (delivery area) this "
            "address belongs to."
        ),
    )

    class Meta:
        model = CustomerAddress
        fields = [
            "address_type",
            "first_name",
            "last_name",
            "company",
            "address_1",
            "address_2",
            "city",
            "state",
            "postcode",
            "country",
            "phone",
            "shipping_zone",
        ]
