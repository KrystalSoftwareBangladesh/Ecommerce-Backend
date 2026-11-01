# email_api/serializers/order_notification_recipient.py
from rest_framework import serializers

from email_api.models import OrderNotificationRecipient
from email_api.services.order_notification import (
    create_order_notification_recipient,
    normalize_recipient_email,
    update_order_notification_recipient,
)


class OrderNotificationRecipientListSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderNotificationRecipient
        fields = [
            'id',
            'email',
            'name',
            'is_active',
            'created_at',
            'updated_at',
        ]


class OrderNotificationRecipientDetailSerializer(
    serializers.ModelSerializer
):
    created_by = serializers.StringRelatedField(read_only=True)
    updated_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = OrderNotificationRecipient
        fields = [
            'id',
            'email',
            'name',
            'is_active',
            'created_at',
            'updated_at',
            'created_by',
            'updated_by',
        ]


class OrderNotificationRecipientWriteSerializer(
    serializers.ModelSerializer
):
    class Meta:
        model = OrderNotificationRecipient
        fields = [
            'id',
            'email',
            'name',
            'is_active',
        ]
        read_only_fields = ['id']

    def validate_email(self, value):
        email = normalize_recipient_email(value)
        qs = OrderNotificationRecipient.objects.filter(
            email__iexact=email,
            deleted_at__isnull=True,
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                'This email address is already a recipient.'
            )
        return email

    def validate_name(self, value):
        return (value or '').strip()

    def create(self, validated_data):
        return create_order_notification_recipient(
            validated_data=validated_data,
            user=self.context['request'].user,
        )

    def update(self, instance, validated_data):
        return update_order_notification_recipient(
            recipient=instance,
            validated_data=validated_data,
            user=self.context['request'].user,
        )
