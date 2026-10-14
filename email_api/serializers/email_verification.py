# email_api/serializers/email_verificaiton.py
from rest_framework import serializers


class EmailVerificationConfirmSerializer(serializers.Serializer):
    token = serializers.CharField(trim_whitespace=True)


class EmailVerificationConfirmResponseSerializer(serializers.Serializer):
    message = serializers.CharField()


class EmailVerificationStatusResponseSerializer(serializers.Serializer):
    email = serializers.EmailField(allow_null=True)
    email_verified = serializers.BooleanField()
