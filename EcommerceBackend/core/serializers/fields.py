# EcommerceBackend/core/serializers/fields.py
from rest_framework import serializers


class AbsoluteImageField(serializers.ImageField):

    def to_representation(self, value):
        url = super().to_representation(value)

        if not url:
            return None

        if url.startswith(("http://", "https://")):
            return url

        request = self.context.get("request")

        if request:
            return request.build_absolute_uri(url)

        return url
