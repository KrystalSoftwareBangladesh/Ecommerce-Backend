# cms_api/serializers/cms_redirect.py
"""Redirect read shapes (docs/cms-architecture.md §6, §9)."""
from rest_framework import serializers

from wagtail.contrib.redirects.models import Redirect

from cms_api.services import published_url_path


class CmsRedirectSerializer(serializers.ModelSerializer):
    current_path = serializers.SerializerMethodField()

    class Meta:
        model = Redirect
        fields = [
            "id",
            "old_path",
            "current_path",
            "is_permanent",
            "automatically_created",
            "created_at",
        ]
        read_only_fields = fields

    def get_current_path(self, instance):
        if not instance.redirect_page_id:
            return instance.redirect_link or None
        return published_url_path(instance.redirect_page.specific)


class CmsRedirectResolveSerializer(serializers.Serializer):
    path = serializers.CharField(read_only=True)
