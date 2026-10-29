# meta_api/serializers/sitemap.py
from rest_framework import serializers


class SitemapUrlSerializer(serializers.Serializer):
    slug = serializers.CharField()
    lastmod = serializers.DateTimeField()


class SitemapUrlsSerializer(serializers.Serializer):
    products = SitemapUrlSerializer(many=True)
    categories = SitemapUrlSerializer(many=True)
    brands = SitemapUrlSerializer(many=True)
    blogs = SitemapUrlSerializer(many=True)
