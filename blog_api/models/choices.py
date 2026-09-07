# blog_api/models/choices.py
from django.db import models


class BlogPostStatus(models.TextChoices):
    """
    Publication state of a blog post.

    A post is always created as `DRAFT`. The move to `PUBLISHED` and back
    is a domain operation carried out by
    `blog_api.services.blog_post.publish_blog_post` /
    `unpublish_blog_post`, never an ordinary field write, so the two
    transitions can be permissioned separately from create and change.
    """
    DRAFT = 'DRAFT', 'Draft'
    PUBLISHED = 'PUBLISHED', 'Published'
