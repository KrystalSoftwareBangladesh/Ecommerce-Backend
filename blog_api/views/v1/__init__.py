# blog_api/views/v1/__init__.py
from .blog_post import BlogPostViewSet
from .blog_tag import BlogTagViewSet


__all__ = [
    "BlogPostViewSet",
    "BlogTagViewSet",
]
