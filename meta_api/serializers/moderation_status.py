# meta_api/serializers/moderation_status.py
from rest_framework import serializers


class ModerationStatusChoiceSerializer(serializers.Serializer):
    key = serializers.CharField()
    value = serializers.IntegerField()
    label = serializers.CharField()
