# customer_api/serializers/customer_address.py
from rest_framework import serializers

from customer_api.models import CustomerAddress


class CustomerAddressListSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerAddress
        fields = [
            "id",
            "address_type",
            "first_name",
            "last_name",
            "phone",
            "city",
            "state",
            "country",
            "created_at",
        ]


class CustomerAddressDetailSerializer(serializers.ModelSerializer):
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
            "created_at",
            "updated_at",
        ]


class CustomerAddressCreateUpdateSerializer(serializers.ModelSerializer):
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
        ]
