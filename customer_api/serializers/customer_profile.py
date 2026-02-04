from django.contrib.auth import get_user_model

from rest_framework import serializers

import uuid

from customer_api.models import CustomerProfile

User = get_user_model()


class CustomerProfileCreateSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(required=True, write_only=True)
    last_name = serializers.CharField(
        required=False, default="", write_only=True)
    middle_name = serializers.CharField(
        required=False, default="", write_only=True)
    email = serializers.EmailField(
        required=False, allow_blank=True, write_only=True)

    class Meta:
        model = CustomerProfile
        fields = [
            "first_name", "middle_name", "last_name",
            "email", "phone", "facebook_profile_url",
            "customer_type", "notes",
        ]

    def validate_email(self, value):
        if value and User.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                "A user with this email already exists.")
        return value

    def create(self, validated_data):
        first_name = validated_data.pop("first_name")
        middle_name = validated_data.pop("middle_name", None)
        last_name = validated_data.pop("last_name", None)
        email = validated_data.pop("email", None)

        user = User.objects.create(
            username=email if email else str(uuid.uuid4()),
            email=email,
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
        )
        user.set_unusable_password()
        user.save()

        profile = CustomerProfile.objects.create(user=user, **validated_data)
        return profile


class CustomerProfileUpdateSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(
        source="user.first_name", required=False)
    middle_name = serializers.CharField(
        source="user.middle_name", required=False)
    last_name = serializers.CharField(source="user.last_name", required=False)

    class Meta:
        model = CustomerProfile
        fields = [
            "first_name", "middle_name", "last_name",
            "phone", "facebook_profile_url",
            "customer_type", "notes",
        ]

    def update(self, instance, validated_data):
        user_data = validated_data.pop("user", {})
        for attr, value in user_data.items():
            setattr(instance.user, attr, value)
        instance.user.save()

        return super().update(instance, validated_data)


class CustomerProfileListSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = CustomerProfile
        fields = ["id", "full_name", "email", "phone",
                  "facebook_profile_url", "customer_type", "created_at"]


class CustomerProfileDetailSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(
        source="user.first_name", read_only=True)
    middle_name = serializers.CharField(
        source="user.middle_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)

    class Meta:
        model = CustomerProfile
        fields = [
            "id", "full_name", "email", "first_name", "middle_name",
            "last_name", "phone", "facebook_profile_url", "customer_type",
            "notes", "is_active", "created_at", "updated_at",
        ]
