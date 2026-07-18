from rest_framework import serializers

from origin_api.models import Origin


class OriginListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Origin
        fields = ['id', 'name', 'slug', 'is_active']


class OriginDetailSerializer(serializers.ModelSerializer):
    created_by = serializers.StringRelatedField()
    updated_by = serializers.StringRelatedField()

    class Meta:
        model = Origin
        fields = '__all__'
        read_only_fields = [
            'created_by', 'updated_by', 'created_at', 'updated_at',
            'is_active', 'deleted_at', 'slug',
        ]


class OriginSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Origin
        fields = ['id', 'slug', 'name']
        read_only_fields = [
            'id', 'name', 'slug',
        ]


class OriginCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Origin
        fields = ['id', 'name', 'description', 'legacy_id']

    def validate_name(self, value):
        queryset = Origin.objects.filter(name__iexact=value, is_active=True)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                'An origin with this name already exists.'
            )
        return value
