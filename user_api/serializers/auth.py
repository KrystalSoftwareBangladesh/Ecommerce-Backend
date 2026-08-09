# user_api/serializers/auth.py
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken

from django.contrib.auth.password_validation import validate_password
from django.db import transaction

from user_api.models import User


class TokenSerializer(serializers.Serializer):
    credential = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        credential = attrs["credential"]
        password = attrs["password"]
        credential = credential.lower()

        user = self._get_user(credential, password)
        if not user:
            raise AuthenticationFailed("Invalid credentials")

        refresh = RefreshToken.for_user(user)

        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user_id": user.id,
            "email": user.email,
            "username": user.username,
            "roles": [g.name for g in user.groups.all()],
            "message": "Login successful",
        }

    def _get_user(self, credential, password):
        user = (
            User.objects.filter(email=credential).first()
            or User.objects.filter(username=credential).first()
        )

        if user and user.check_password(password):
            return user
        return None


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(
        write_only=True, required=True, validators=[validate_password])
    confirm_new_password = serializers.CharField(
        write_only=True, required=True)

    def validate(self, data):
        """
            Ensure old password is correct and new passwords match.
        """
        user = self.context['request'].user

        if not user.check_password(data['old_password']):
            raise serializers.ValidationError({"old_password": "Incorrect old password."})  # noqa

        if data['new_password'] != data['confirm_new_password']:
            raise serializers.ValidationError({"new_password": "New passwords do not match."})  # noqa

        return data

    def update(self, instance, validated_data):
        """
            Update user's password.
        """
        instance.set_password(validated_data['new_password'])
        instance.save()
        return instance


class CustomerSignupSerializer(serializers.Serializer):
    """
    Serializer for customer registration (public signup).
    Creates User + CustomerProfile atomically.
    """
    email = serializers.EmailField(write_only=True, required=True)
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        style={'input_type': 'password'}
    )
    confirm_password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )
    first_name = serializers.CharField(write_only=True, required=True)
    last_name = serializers.CharField(
        write_only=True, required=False, allow_blank=True, default=""
    )
    middle_name = serializers.CharField(
        write_only=True, required=False, allow_blank=True, default=""
    )
    phone = serializers.CharField(required=False, allow_blank=True)

    # Read-only response fields
    id = serializers.IntegerField(read_only=True)
    user_id = serializers.IntegerField(read_only=True)
    customer_type = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    refresh = serializers.CharField(read_only=True)
    access = serializers.CharField(read_only=True)

    def validate_email(self, value):
        """Ensure email is unique."""
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                "A user with this email already exists."
            )
        return value

    def validate(self, data):
        """Validate password confirmation."""
        password = data.get('password')
        confirm_password = data.get('confirm_password')

        if password != confirm_password:
            raise serializers.ValidationError({
                'confirm_password': 'Passwords do not match.'
            })

        return data

    @transaction.atomic
    def create(self, validated_data):
        """
        Create User and CustomerProfile atomically.
        Return customer profile with JWT tokens.
        """
        from customer_api.models import CustomerProfile

        # Extract data
        email = validated_data.pop('email')
        email = email.lower()
        password = validated_data.pop('password')
        validated_data.pop('confirm_password')  # Remove confirm_password

        first_name = validated_data.pop('first_name')
        last_name = validated_data.pop('last_name', '')
        middle_name = validated_data.pop('middle_name', '')
        phone = validated_data.pop('phone', '')

        # Create User with email as both email and username
        user = User.objects.create_user(
            email=email,
            username=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            middle_name=middle_name,
            role='CUSTOMER',
            is_active=True,
        )

        # Create CustomerProfile
        profile = CustomerProfile.objects.create(
            user=user,
            phone=phone,
            customer_type='WEBSITE',
        )

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)

        # Return profile with tokens
        return {
            'id': profile.id,
            'user_id': user.id,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'middle_name': user.middle_name,
            'phone': profile.phone,
            'customer_type': profile.customer_type,
            'created_at': profile.created_at,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }

    def to_representation(self, instance):
        """Return the created customer data with tokens."""
        return instance


class ChangeUserPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
    )
    confirm_password = serializers.CharField(
        write_only=True,
        required=True,
    )

    def validate(self, attrs):
        password = attrs.get("password")
        confirm_password = attrs.get("confirm_password")

        if password != confirm_password:
            raise serializers.ValidationError({
                "password": "Password do not match."
            })

        return attrs

    def update(self, instance, validated_data):
        password = validated_data["password"]

        instance.set_password(password)
        instance.save(update_fields=["password"])

        return instance
