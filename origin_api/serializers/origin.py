# origin_api/serializer/origin.py
from drf_spectacular.helpers import lazy_serializer
from drf_spectacular.utils import extend_schema_field

from rest_framework import serializers

from origin_api.models import Origin


class OriginSummarySerializer(serializers.ModelSerializer):
    parent = serializers.SerializerMethodField()

    class Meta:
        model = Origin
        fields = ['id', 'slug', 'name', 'parent']
        read_only_fields = ['id', 'slug', 'name', 'parent']

    @extend_schema_field(
        lazy_serializer(
            "origin_api.serializers.origin.OriginSummarySerializer")()
    )
    def get_parent(self, obj):
        if obj.parent is None:
            return None
        return OriginSummarySerializer(obj.parent, context=self.context).data


class OriginListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Origin
        fields = ['id', 'name', 'slug', 'is_active']


class OriginDetailSerializer(serializers.ModelSerializer):
    created_by = serializers.StringRelatedField()
    updated_by = serializers.StringRelatedField()
    parent = OriginSummarySerializer(read_only=True)

    class Meta:
        model = Origin
        fields = '__all__'
        read_only_fields = [
            'created_by', 'updated_by', 'created_at', 'updated_at',
            'is_active', 'deleted_at', 'slug',
        ]


class OriginCreateSerializer(serializers.ModelSerializer):
    parent = serializers.PrimaryKeyRelatedField(
        queryset=Origin.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Origin
        fields = ['id', 'name', 'parent', 'description', 'legacy_id']

    def validate_name(self, value):
        queryset = Origin.objects.filter(name__iexact=value, is_active=True)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                'An origin with this name already exists.'
            )
        return value


class OriginUpdateSerializer(serializers.ModelSerializer):
    parent = serializers.PrimaryKeyRelatedField(
        queryset=Origin.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Origin
        fields = ['id', 'name', 'parent', 'slug', 'description', 'legacy_id']

    def validate_name(self, value):
        queryset = Origin.objects.filter(name__iexact=value, is_active=True)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                'An origin with this name already exists.'
            )
        return value
